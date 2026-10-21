// Fixed screen-size target, independent of plan zoom, contrast and brightness.
export function drawMeasureTarget(ctx, point, zoom) {
  ctx.save();
  ctx.setLineDash([]);
  ctx.shadowBlur = 0;
  ctx.globalAlpha = 1;
  ctx.beginPath();
  ctx.arc(point[0], point[1], 5 / zoom, 0, Math.PI * 2);
  ctx.strokeStyle = "#ffffff";
  ctx.lineWidth = 4 / zoom;
  ctx.stroke();
  ctx.strokeStyle = "#000000";
  ctx.lineWidth = 2 / zoom;
  ctx.stroke();
  ctx.restore();
}