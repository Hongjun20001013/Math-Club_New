/**
 * Novel Prep — smart ink v6: corner-count gates + fit-error tiebreak.
 */
(function (global) {
  "use strict";

  function dist(a, b) {
    return Math.hypot(a[0] - b[0], a[1] - b[1]);
  }

  function xy(p) {
    return [p[0], p[1]];
  }

  function stripTimestamps(points) {
    return points.map(function (p) { return [p[0], p[1]]; });
  }

  function pathLength(points) {
    var len = 0;
    for (var i = 1; i < points.length; i++) len += dist(points[i - 1], points[i]);
    return len;
  }

  function boundingBox(points) {
    var minX = 1, minY = 1, maxX = 0, maxY = 0;
    points.forEach(function (p) {
      minX = Math.min(minX, p[0]);
      minY = Math.min(minY, p[1]);
      maxX = Math.max(maxX, p[0]);
      maxY = Math.max(maxY, p[1]);
    });
    return { minX: minX, minY: minY, maxX: maxX, maxY: maxY, w: maxX - minX, h: maxY - minY };
  }

  function centroid(points) {
    var sx = 0, sy = 0;
    points.forEach(function (p) { sx += p[0]; sy += p[1]; });
    return [sx / points.length, sy / points.length];
  }

  function straightness(points) {
    if (points.length < 2) return 1;
    var d = dist(points[0], points[points.length - 1]);
    return pathLength(points) < 1e-6 ? 1 : d / pathLength(points);
  }

  function resample(points, targetCount) {
    if (points.length <= 2) return points.slice();
    var total = pathLength(points);
    if (total < 1e-6) return points.slice(0, 1);
    var step = total / Math.max(8, targetCount - 1);
    var out = [points[0].slice()];
    var acc = 0;
    var i = 1;
    while (i < points.length && out.length < targetCount) {
      var seg = dist(points[i - 1], points[i]);
      if (acc + seg >= step) {
        var t = (step - acc) / Math.max(seg, 1e-9);
        out.push([
          points[i - 1][0] + t * (points[i][0] - points[i - 1][0]),
          points[i - 1][1] + t * (points[i][1] - points[i - 1][1]),
        ]);
        points[i - 1] = out[out.length - 1];
        acc = 0;
      } else {
        acc += seg;
        i += 1;
      }
    }
    if (out[out.length - 1] !== points[points.length - 1]) {
      out.push(points[points.length - 1].slice());
    }
    return out;
  }

  function isClosed(points, diag) {
    diag = diag || Math.hypot(boundingBox(points).w, boundingBox(points).h);
    var gap = dist(points[0], points[points.length - 1]);
    var peri = pathLength(points);
    return gap < Math.max(0.028, diag * 0.38, peri * 0.28);
  }

  function pointLineDistance(p, a, b) {
    var dx = b[0] - a[0];
    var dy = b[1] - a[1];
    if (Math.abs(dx) < 1e-9 && Math.abs(dy) < 1e-9) return dist(p, a);
    var t = ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / (dx * dx + dy * dy);
    t = Math.max(0, Math.min(1, t));
    return dist(p, [a[0] + t * dx, a[1] + t * dy]);
  }

  function rdp(points, epsilon) {
    if (points.length <= 2) return points.slice();
    var first = points[0];
    var last = points[points.length - 1];
    var index = -1;
    var maxDist = 0;
    for (var i = 1; i < points.length - 1; i++) {
      var d = pointLineDistance(points[i], first, last);
      if (d > maxDist) {
        index = i;
        maxDist = d;
      }
    }
    if (maxDist > epsilon) {
      var left = rdp(points.slice(0, index + 1), epsilon);
      var right = rdp(points.slice(index), epsilon);
      return left.slice(0, -1).concat(right);
    }
    return [first, last];
  }

  function angleAt(a, b, c) {
    var v1x = a[0] - b[0], v1y = a[1] - b[1];
    var v2x = c[0] - b[0], v2y = c[1] - b[1];
    var d1 = Math.hypot(v1x, v1y);
    var d2 = Math.hypot(v2x, v2y);
    if (d1 < 1e-9 || d2 < 1e-9) return 180;
    var cos = (v1x * v2x + v1y * v2y) / (d1 * d2);
    return (Math.acos(Math.max(-1, Math.min(1, cos))) * 180) / Math.PI;
  }

  function findSharpCorners(points, minTurnDeg, mergeDist) {
    minTurnDeg = minTurnDeg || 28;
    mergeDist = mergeDist == null ? 0.025 : mergeDist;
    var corners = [];
    for (var i = 1; i < points.length - 1; i++) {
      var turn = 180 - angleAt(points[i - 1], points[i], points[i + 1]);
      if (turn >= minTurnDeg) corners.push(points[i].slice());
    }
    return mergeNearbyPoints(corners, mergeDist);
  }

  function rotateLoopStart(points) {
    if (points.length < 4) return points.slice();
    var anchor = points[0];
    var bestIdx = 0;
    var bestDist = 0;
    for (var i = 1; i < points.length; i++) {
      var d = dist(anchor, points[i]);
      if (d > bestDist) {
        bestDist = d;
        bestIdx = i;
      }
    }
    return points.slice(bestIdx).concat(points.slice(0, bestIdx));
  }

  function simplifyClosed(open, diag, epsFactor) {
    var eps = Math.max(0.003, diag * epsFactor);
    var rotated = rotateLoopStart(open);
    var loop = rotated.concat([rotated[0].slice()]);
    var simp = rdp(loop, eps);
    if (simp.length >= 2 && dist(simp[0], simp[simp.length - 1]) < diag * 0.16) {
      simp = simp.slice(0, -1);
    }
    return simp;
  }

  function mergeNearbyPoints(points, minDist) {
    if (!points.length) return [];
    var out = [points[0].slice()];
    for (var i = 1; i < points.length; i++) {
      if (dist(out[out.length - 1], points[i]) >= minDist) out.push(points[i].slice());
    }
    return out;
  }

  function circularity(points) {
    var c = centroid(points);
    var radii = points.map(function (p) { return dist(p, c); });
    var avg = radii.reduce(function (a, b) { return a + b; }, 0) / radii.length;
    if (avg < 1e-4) return 0;
    var variance =
      radii.reduce(function (acc, r) { return acc + Math.pow(r - avg, 2); }, 0) / radii.length;
    return Math.max(0, 1 - (Math.sqrt(variance) / avg) * 2.4);
  }

  function polygonAngles(corners) {
    var n = corners.length;
    if (n < 3) return [];
    var angles = [];
    for (var i = 0; i < n; i++) {
      angles.push(angleAt(corners[(i + n - 1) % n], corners[i], corners[(i + 1) % n]));
    }
    return angles;
  }

  function isRectAngles(angles) {
    if (angles.length !== 4) return false;
    return angles.every(function (a) { return a > 52 && a < 128; });
  }

  function isRectAnglesLoose(angles) {
    if (angles.length !== 4) return false;
    return angles.every(function (a) { return a > 38 && a < 142; });
  }

  function edgeOccupancy(open, bb, diag) {
    var margin = Math.max(0.008, diag * 0.12);
    var left = 0;
    var right = 0;
    var top = 0;
    var bottom = 0;
    open.forEach(function (p) {
      if (Math.abs(p[0] - bb.minX) < margin) left += 1;
      if (Math.abs(p[0] - bb.maxX) < margin) right += 1;
      if (Math.abs(p[1] - bb.minY) < margin) top += 1;
      if (Math.abs(p[1] - bb.maxY) < margin) bottom += 1;
    });
    var n = Math.max(1, open.length);
    return {
      left: left / n,
      right: right / n,
      top: top / n,
      bottom: bottom / n,
      minSide: Math.min(left, right, top, bottom) / n,
    };
  }

  function hasFourEdgeStructure(open, bb, diag) {
    var occ = edgeOccupancy(open, bb, diag);
    var minHits = Math.max(0.06, 0.08);
    return occ.left >= minHits && occ.right >= minHits && occ.top >= minHits && occ.bottom >= minHits;
  }

  function pickBestQuad(corners) {
    if (corners.length <= 4) return corners.slice(0, 4);
    var best = corners.slice(0, 4);
    var bestScore = -1;
    for (var i = 0; i < corners.length; i++) {
      for (var j = i + 1; j < corners.length; j++) {
        for (var k = j + 1; k < corners.length; k++) {
          for (var l = k + 1; l < corners.length; l++) {
            var quad = [corners[i], corners[j], corners[k], corners[l]];
            var xs = quad.map(function (p) { return p[0]; });
            var ys = quad.map(function (p) { return p[1]; });
            var area = (Math.max.apply(null, xs) - Math.min.apply(null, xs)) *
              (Math.max.apply(null, ys) - Math.min.apply(null, ys));
            var angles = polygonAngles(quad);
            var score = area * (isRectAnglesLoose(angles) ? 1.35 : 1);
            if (score > bestScore) {
              bestScore = score;
              best = quad;
            }
          }
        }
      }
    }
    return best;
  }

  function fitRectangleFromBBox(bb) {
    return {
      kind: "shape",
      shape: "rect",
      x: bb.minX,
      y: bb.minY,
      w: bb.w,
      h: bb.h,
      points: [[bb.minX, bb.minY], [bb.maxX, bb.maxY]],
    };
  }

  function rectAnglePenalty(angles) {
    if (angles.length !== 4) return 1;
    return angles.reduce(function (acc, a) {
      return acc + Math.min(Math.abs(a - 90), 45) / 45;
    }, 0) / 4;
  }

  function idealPathForShape(stroke) {
    if (!stroke || stroke.kind !== "shape") return stroke.points || [];
    var s = stroke.shape;
    if (s === "line") {
      return [[stroke.x1, stroke.y1], [stroke.x2, stroke.y2]];
    }
    if (s === "circle") {
      var pts = [];
      var steps = 48;
      for (var i = 0; i <= steps; i++) {
        var t = (i / steps) * Math.PI * 2;
        pts.push([stroke.cx + Math.cos(t) * stroke.r, stroke.cy + Math.sin(t) * stroke.r]);
      }
      return pts;
    }
    if (s === "triangle" && stroke.points) {
      return stroke.points.concat([stroke.points[0]]);
    }
    if (s === "rect") {
      var x = stroke.x, y = stroke.y, w = stroke.w, h = stroke.h;
      return [[x, y], [x + w, y], [x + w, y + h], [x, y + h], [x, y]];
    }
    return stroke.points || [];
  }

  function pathFitError(strokePoints, idealPoints) {
    if (!strokePoints.length || !idealPoints || idealPoints.length < 2) return Infinity;
    var total = 0;
    strokePoints.forEach(function (p) {
      var best = Infinity;
      for (var i = 0; i < idealPoints.length - 1; i++) {
        best = Math.min(best, pointLineDistance(p, idealPoints[i], idealPoints[i + 1]));
      }
      total += best;
    });
    return total / strokePoints.length;
  }

  function collectRectCandidates(open, diag) {
    var out = [];
    var mergeDist = Math.max(0.008, diag * 0.07);
    var epsList = [0.015, 0.02, 0.03, 0.04, 0.05, 0.065, 0.08, 0.1, 0.13, 0.16, 0.2];
    var seen = {};

    function add(shape, angles) {
      var key = [shape.x, shape.y, shape.w, shape.h].map(function (v) { return v.toFixed(3); }).join(",");
      if (seen[key]) return;
      seen[key] = true;
      out.push({ shape: shape, angles: angles });
    }

    [34, 42, 50].forEach(function (deg) {
      var corners = findSharpCorners(open, deg, mergeDist);
      if (corners.length !== 4) return;
      var angles = polygonAngles(corners);
      if (!isRectAnglesLoose(angles)) return;
      add(fitRectangleFromCorners(corners), angles);
    });

    for (var i = 0; i < epsList.length; i++) {
      var simp = simplifyClosed(open, diag, epsList[i]);
      if (simp.length !== 4) continue;
      var angles = polygonAngles(simp);
      if (!isRectAnglesLoose(angles)) continue;
      add(fitRectangleFromCorners(simp), angles);
    }
    return out;
  }

  function collectTriCandidates(open, diag) {
    var out = [];
    var mergeDist = Math.max(0.008, diag * 0.07);
    var epsList = [0.02, 0.03, 0.04, 0.05, 0.07, 0.09, 0.12];
    var seen = {};

    function add(shape) {
      var pts = shape.points || [];
      var key = pts.map(function (p) { return p[0].toFixed(3) + "," + p[1].toFixed(3); }).join("|");
      if (seen[key]) return;
      seen[key] = true;
      out.push({ shape: shape });
    }

    [32, 38, 44].forEach(function (deg) {
      var corners = findSharpCorners(open, deg, mergeDist);
      if (corners.length === 3) add(fitTriangle(corners));
    });

    for (var i = 0; i < epsList.length; i++) {
      var simp = simplifyClosed(open, diag, epsList[i]);
      if (simp.length === 3) add(fitTriangle(simp));
    }
    return out;
  }

  function classifyClosedShape(open, bb, diag) {
    var mergeDist = Math.max(0.008, diag * 0.07);
    var circ = circularity(open);
    var turn = maxSharpTurn(open);
    var c34 = findSharpCorners(open, 34, mergeDist);
    var c42 = findSharpCorners(open, 42, mergeDist);
    var c50 = findSharpCorners(open, 50, mergeDist);
    var n34 = c34.length;
    var n42 = c42.length;
    var n50 = c50.length;

    var circle = fitCircle(open);
    var cErr = pathFitError(open, idealPathForShape(circle)) / diag;
    var maxErr = 0.28;

    function fitOk(err) {
      return err < maxErr;
    }

    // ── Triangle: exactly 3 strong corners ──
    if (n34 === 3 || n42 === 3) {
      var triPts = n34 === 3 ? c34 : c42;
      var tri = fitTriangle(triPts);
      var tErr = pathFitError(open, idealPathForShape(tri)) / diag;
      if (fitOk(tErr)) return tri;
    }
    var triCands = collectTriCandidates(open, diag);
    for (var ti = 0; ti < triCands.length; ti++) {
      var tShape = triCands[ti].shape;
      var tErr2 = pathFitError(open, idealPathForShape(tShape)) / diag;
      if (fitOk(tErr2) && n42 !== 4) return tShape;
    }

    // ── Circle: round stroke, no rect corners ──
    var rectLike4 = n42 === 4 && isRectAnglesLoose(polygonAngles(c42));
    var rectLike50 = n50 === 4 && isRectAnglesLoose(polygonAngles(c50));
    var hasRectCorners = rectLike4 || rectLike50;

    if (!hasRectCorners && n42 <= 2 && turn < 46) {
      if (fitOk(cErr) && (circ > 0.46 || cErr < 0.13)) return circle;
    }
    if (!hasRectCorners && n50 <= 1 && circ > 0.44 && fitOk(cErr)) return circle;
    if (!hasRectCorners && circ > 0.6 && n42 <= 3 && turn < 40 && fitOk(cErr)) return circle;

    // ── Rectangle: 4 corners near 90° ──
    if (rectLike50) {
      var rect50 = fitRectangleFromCorners(c50);
      var rErr50 = pathFitError(open, idealPathForShape(rect50)) / diag;
      if (fitOk(rErr50) && n34 !== 3) return rect50;
    }
    if (rectLike4) {
      var rect42 = fitRectangleFromCorners(c42);
      var rErr42 = pathFitError(open, idealPathForShape(rect42)) / diag;
      if (fitOk(rErr42) && n34 !== 3) return rect42;
    }
    var rectCands = collectRectCandidates(open, diag);
    for (var ri = 0; ri < rectCands.length; ri++) {
      var rShape = rectCands[ri].shape;
      var rErr = pathFitError(open, idealPathForShape(rShape)) / diag;
      if (fitOk(rErr) && n34 !== 3 && rErr + 0.03 < cErr) return rShape;
    }

    // Bbox rect last resort — only when clearly not a circle or triangle
    if (n34 !== 3 && n42 !== 3 && circ < 0.58 && turn < 48) {
      var bboxRect = fitRectangleFromBBox(bb);
      var bboxErr = pathFitError(open, idealPathForShape(bboxRect)) / diag;
      if (fitOk(bboxErr) && bboxErr + 0.05 < cErr) return bboxRect;
    }

    // ── Fallback: pick lowest fit-error among allowed types ──
    var pool = [];
    if (n42 <= 3 || circ > 0.42) {
      pool.push({ shape: circle, err: cErr - Math.max(0, circ - 0.5) * 0.06, type: "circle" });
    }
    triCands.forEach(function (t) {
      pool.push({
        shape: t.shape,
        err: pathFitError(open, idealPathForShape(t.shape)) / diag,
        type: "triangle",
      });
    });
    rectCands.forEach(function (r) {
      if (!isRectAnglesLoose(r.angles)) return;
      pool.push({
        shape: r.shape,
        err: pathFitError(open, idealPathForShape(r.shape)) / diag + (circ > 0.68 ? 0.08 : 0),
        type: "rect",
      });
    });

    if (!pool.length) return null;
    pool.sort(function (a, b) { return a.err - b.err; });
    var best = pool[0];
    if (!best || best.err > maxErr) return null;

    if (pool.length > 1 && pool[1].err - best.err < 0.025) {
      if (best.type === "rect" && circ > 0.58 && n42 <= 2) {
        var circItem = pool.find(function (p) { return p.type === "circle"; });
        if (circItem) best = circItem;
      } else if (best.type === "circle" && hasRectCorners) {
        var rectItem = pool.find(function (p) { return p.type === "rect"; });
        if (rectItem) best = rectItem;
      } else if (best.type === "circle" && n34 === 3) {
        var triItem = pool.find(function (p) { return p.type === "triangle"; });
        if (triItem) best = triItem;
      }
    }
    return best.shape;
  }

  function isTriangleAngles(angles) {
    if (angles.length !== 3) return false;
    var sum = angles.reduce(function (acc, a) { return acc + a; }, 0);
    return sum > 140 && sum < 220;
  }

  function maxSharpTurn(points) {
    var maxTurn = 0;
    for (var i = 1; i < points.length - 1; i++) {
      maxTurn = Math.max(maxTurn, 180 - angleAt(points[i - 1], points[i], points[i + 1]));
    }
    return maxTurn;
  }

  function triangleArea(a, b, c) {
    return Math.abs((b[0] - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (b[1] - a[1])) / 2;
  }

  function fitCircle(points) {
    var c = centroid(points);
    var avgR =
      points.reduce(function (acc, p) { return acc + dist(p, c); }, 0) / points.length;
    avgR = Math.max(0.008, avgR);
    return {
      kind: "shape",
      shape: "circle",
      cx: c[0],
      cy: c[1],
      r: avgR,
      points: [[c[0], c[1]], [c[0] + avgR, c[1]]],
    };
  }

  function fitLine(a, b) {
    return {
      kind: "shape",
      shape: "line",
      x1: a[0], y1: a[1], x2: b[0], y2: b[1],
      points: [a.slice(), b.slice()],
    };
  }

  function fitTriangle(corners) {
    var pts = corners.slice(0, 3);
    while (pts.length < 3) pts.push(pts[pts.length - 1].slice());
    return {
      kind: "shape",
      shape: "triangle",
      points: pts.map(function (p) { return [p[0], p[1]]; }),
    };
  }

  function fitRectangleFromCorners(corners) {
    var xs = corners.map(function (p) { return p[0]; });
    var ys = corners.map(function (p) { return p[1]; });
    var minX = Math.min.apply(null, xs);
    var maxX = Math.max.apply(null, xs);
    var minY = Math.min.apply(null, ys);
    var maxY = Math.max.apply(null, ys);
    return {
      kind: "shape",
      shape: "rect",
      x: minX, y: minY, w: maxX - minX, h: maxY - minY,
      points: [[minX, minY], [maxX, maxY]],
    };
  }

  function pickBestTriangle(corners) {
    if (corners.length <= 3) return fitTriangle(corners);
    var best = corners.slice(0, 3);
    var bestArea = triangleArea(best[0], best[1], best[2]);
    for (var i = 0; i < corners.length; i++) {
      for (var j = i + 1; j < corners.length; j++) {
        for (var k = j + 1; k < corners.length; k++) {
          var area = triangleArea(corners[i], corners[j], corners[k]);
          if (area > bestArea) {
            bestArea = area;
            best = [corners[i], corners[j], corners[k]];
          }
        }
      }
    }
    return fitTriangle(best);
  }

  function detectShape(rawPoints) {
    if (!rawPoints || rawPoints.length < 3) return null;
    var points = resample(stripTimestamps(rawPoints), 96);
    var bb = boundingBox(points);
    var diag = Math.hypot(bb.w, bb.h);
    if (diag < 0.01) return null;

    var closed = isClosed(points, diag);
    var lineScore = straightness(points);

    if (!closed && lineScore > 0.84 && points.length >= 2) {
      return fitLine(points[0], points[points.length - 1]);
    }

    if (closed) {
      var open = points.slice();
      if (dist(open[0], open[open.length - 1]) > 1e-6) open.push(open[0].slice());
      open = open.slice(0, -1);

      var classified = classifyClosedShape(open, bb, diag);
      if (classified) return classified;
    }

    if (lineScore > 0.78) {
      return fitLine(points[0], points[points.length - 1]);
    }

    return null;
  }

  function shapeToPoints(stroke) {
    if (!stroke || stroke.kind !== "shape") return stroke.points || [];
    var s = stroke.shape;
    if (s === "line") {
      return [[stroke.x1, stroke.y1], [stroke.x2, stroke.y2]];
    }
    if (s === "circle") {
      var pts = [];
      var steps = 64;
      for (var i = 0; i <= steps; i++) {
        var t = (i / steps) * Math.PI * 2;
        pts.push([stroke.cx + Math.cos(t) * stroke.r, stroke.cy + Math.sin(t) * stroke.r]);
      }
      return pts;
    }
    if (s === "triangle" && stroke.points) return stroke.points.concat([stroke.points[0]]);
    if (s === "rect") {
      var x = stroke.x, y = stroke.y, w = stroke.w, h = stroke.h;
      return [[x, y], [x + w, y], [x + w, y + h], [x, y + h], [x, y]];
    }
    return stroke.points || [];
  }

  function sampleStrokePoints(stroke) {
    if (stroke.kind === "stamp" || stroke.kind === "latex") return [[stroke.x, stroke.y]];
    if (stroke.kind === "shape") return shapeToPoints(stroke);
    return stroke.points || [];
  }

  function catmullRomPath(ctx, points, bw, bh) {
    if (points.length < 2) return;
    ctx.moveTo(points[0][0] * bw, points[0][1] * bh);
    if (points.length === 2) {
      ctx.lineTo(points[1][0] * bw, points[1][1] * bh);
      return;
    }
    for (var i = 0; i < points.length - 1; i++) {
      var p0 = points[i - 1] || points[i];
      var p1 = points[i];
      var p2 = points[i + 1];
      var p3 = points[i + 2] || p2;
      var cp1x = p1[0] + (p2[0] - p0[0]) / 6;
      var cp1y = p1[1] + (p2[1] - p0[1]) / 6;
      var cp2x = p2[0] - (p3[0] - p1[0]) / 6;
      var cp2y = p2[1] - (p3[1] - p1[1]) / 6;
      ctx.bezierCurveTo(cp1x * bw, cp1y * bh, cp2x * bw, cp2y * bh, p2[0] * bw, p2[1] * bh);
    }
  }

  function drawProStroke(ctx, stroke, bw, bh, dpr, opts) {
    opts = opts || {};
    var points = stroke.points || [];
    if (points.length < 2) return;
    var baseW = (stroke.width || 3) * (dpr || 1);
    var pro = opts.pro !== false && stroke.tool !== "highlighter";
    ctx.save();
    ctx.strokeStyle = stroke.color || "#5b3df5";
    ctx.globalAlpha = stroke.alpha == null ? 1 : stroke.alpha;
    ctx.lineCap = "round";
    ctx.lineJoin = "round";

    if (!pro || stroke.tool === "highlighter") {
      ctx.lineWidth = baseW;
      ctx.beginPath();
      catmullRomPath(ctx, points, bw, bh);
      ctx.stroke();
      ctx.restore();
      return;
    }

    for (var i = 1; i < points.length; i++) {
      var p0 = points[i - 1];
      var p1 = points[i];
      var seg = dist(p0, p1);
      var dt = (p1[2] != null && p0[2] != null) ? Math.max(1, p1[2] - p0[2]) : 16;
      var velocity = seg / dt;
      var pressure = Math.max(0.35, Math.min(1.18, 1.08 - velocity * 16));
      ctx.lineWidth = baseW * pressure;
      ctx.beginPath();
      ctx.moveTo(p0[0] * bw, p0[1] * bh);
      ctx.lineTo(p1[0] * bw, p1[1] * bh);
      ctx.stroke();
    }
    ctx.restore();
  }

  function drawShape(ctx, stroke, bw, bh, dpr) {
    var pts = shapeToPoints(stroke);
    if (pts.length < 2) return;
    var lw = (stroke.width || 3) * (dpr || 1);
    ctx.save();
    ctx.strokeStyle = stroke.color || "#5b3df5";
    ctx.globalAlpha = stroke.alpha == null ? 1 : stroke.alpha;
    ctx.lineWidth = lw;
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    ctx.beginPath();
    ctx.moveTo(pts[0][0] * bw, pts[0][1] * bh);
    for (var i = 1; i < pts.length; i++) {
      ctx.lineTo(pts[i][0] * bw, pts[i][1] * bh);
    }
    ctx.stroke();
    ctx.restore();
  }

  function drawStamp(ctx, stroke, bw, bh) {
    if (!stroke.text) return;
    var sizePx = Math.max(14, (stroke.size || 0.028) * bh);
    ctx.save();
    ctx.fillStyle = stroke.color || "#5b3df5";
    ctx.globalAlpha = stroke.alpha == null ? 1 : stroke.alpha;
    ctx.font = "600 " + sizePx + "px 'Source Serif 4', 'Times New Roman', serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(stroke.text, stroke.x * bw, stroke.y * bh);
    ctx.restore();
  }

  function drawStroke(ctx, stroke, bw, bh, dpr, opts) {
    if (!stroke) return;
    if (stroke.kind === "latex") return;
    if (stroke.kind === "stamp") {
      drawStamp(ctx, stroke, bw, bh);
      return;
    }
    if (stroke.kind === "shape") {
      drawShape(ctx, stroke, bw, bh, dpr);
      return;
    }
    drawProStroke(ctx, stroke, bw, bh, dpr, opts);
  }

  function finalizeStroke(stroke, tool) {
    if (!stroke || !stroke.points || stroke.points.length < 2) return stroke;
    if (tool === "smart") {
      var detected = detectShape(stroke.points);
      if (detected) {
        detected.color = stroke.color;
        detected.width = stroke.width;
        detected.alpha = stroke.alpha;
        detected.tool = tool;
        return detected;
      }
    }
    return stroke;
  }

  function createStamp(text, x, y, color, sizeNorm) {
    return {
      kind: "stamp",
      text: text,
      x: x,
      y: y,
      size: sizeNorm || 0.032,
      color: color || "#5b3df5",
      alpha: 1,
      tool: "math",
      points: [[x, y], [x, y]],
    };
  }

  function createLatexStamp(latex, x, y, color, sizeNorm) {
    return {
      kind: "latex",
      latex: latex,
      x: x,
      y: y,
      size: sizeNorm || 0.038,
      color: color || "#5b3df5",
      alpha: 1,
      tool: "math",
      points: [[x, y], [x, y]],
    };
  }

  function normalizeLatexLine(raw) {
    var s = String(raw || "").trim();
    if (!s) return "";
    s = s.replace(/\$/g, "");
    s = s.replace(/(\d+)\/(\d+)/g, "\\frac{$1}{$2}");
    s = s.replace(/(\w)\^(\d+)/g, "$1^{$2}");
    s = s.replace(/(\w)\^(\([^)]+\))/g, "$1^{$2}");
    s = s.replace(/sqrt\(([^)]+)\)/gi, "\\sqrt{$1}");
    s = s.replace(/pi\b/gi, "\\pi ");
    s = s.replace(/theta\b/gi, "\\theta ");
    return s;
  }

  function normalizeLatexInput(raw) {
    var lines = String(raw || "").split(/\r?\n/).map(normalizeLatexLine).filter(Boolean);
    if (!lines.length) return "";
    if (lines.length === 1) return lines[0];
    return "\\begin{aligned}" + lines.join(" \\\\ ") + "\\end{aligned}";
  }

  var MATH_STAMPS = [
    { t: "π", label: "Pi", latex: "\\pi" },
    { t: "θ", label: "Theta", latex: "\\theta" },
    { t: "α", label: "Alpha", latex: "\\alpha" },
    { t: "√", label: "Sqrt", latex: "\\sqrt{x}" },
    { t: "∫", label: "Integral", latex: "\\int" },
    { t: "∑", label: "Sum", latex: "\\sum" },
    { t: "∞", label: "Infinity", latex: "\\infty" },
    { t: "±", label: "Plus-minus", latex: "\\pm" },
    { t: "≤", label: "Less equal", latex: "\\leq" },
    { t: "≥", label: "Greater equal", latex: "\\geq" },
    { t: "°", label: "Degree", latex: "^\\circ" },
    { t: "²", label: "Squared", latex: "^2" },
    { t: "½", label: "Half", latex: "\\frac{1}{2}" },
    { t: "×", label: "Times", latex: "\\times" },
    { t: "÷", label: "Divide", latex: "\\div" },
  ];

  var FORMULA_KEYS = [
    { label: "x²", insert: "x^{2}" },
    { label: "xⁿ", insert: "x^{n}" },
    { label: "a/b", insert: "\\frac{a}{b}" },
    { label: "√x", insert: "\\sqrt{x}" },
    { label: "sin", insert: "\\sin\\left(x\\right)" },
    { label: "cos", insert: "\\cos\\left(x\\right)" },
    { label: "tan", insert: "\\tan\\left(x\\right)" },
    { label: "log", insert: "\\log\\left(x\\right)" },
    { label: "ln", insert: "\\ln\\left(x\\right)" },
    { label: "→", insert: "\\rightarrow" },
    { label: "±", insert: "\\pm" },
    { label: "≠", insert: "\\neq" },
  ];

  global.NpInkSmart = {
    detectShape: detectShape,
    finalizeStroke: finalizeStroke,
    drawStroke: drawStroke,
    sampleStrokePoints: sampleStrokePoints,
    createStamp: createStamp,
    createLatexStamp: createLatexStamp,
    normalizeLatexInput: normalizeLatexInput,
    MATH_STAMPS: MATH_STAMPS,
    FORMULA_KEYS: FORMULA_KEYS,
    dist: dist,
  };
})(typeof window !== "undefined" ? window : globalThis);
