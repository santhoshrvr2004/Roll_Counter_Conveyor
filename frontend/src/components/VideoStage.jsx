import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { CameraIcon, CrosshairIcon, ExpandIcon, StopIcon } from './Icons';

export default function VideoStage({
  frameUrl,
  frameSize,
  drawMode,
  onGeometry,
  connected,
  onCancelDraw,
  messageText,
  setupComplete,
}) {
  const shellRef = useRef(null);
  const imageRef = useRef(null);
  const canvasRef = useRef(null);
  const dragRef = useRef(null);
  const [draft, setDraft] = useState(null);

  const imageSize = useMemo(() => {
    if (frameSize?.width && frameSize?.height) return frameSize;
    const img = imageRef.current;
    if (img?.naturalWidth && img?.naturalHeight) {
      return { width: img.naturalWidth, height: img.naturalHeight };
    }
    return { width: 640, height: 480 };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [frameSize, frameUrl]);

  const metrics = useCallback(() => {
    const shell = shellRef.current;
    if (!shell) return null;
    const rect = shell.getBoundingClientRect();
    const scale = Math.min(rect.width / imageSize.width, rect.height / imageSize.height);
    const width = imageSize.width * scale;
    const height = imageSize.height * scale;
    return {
      rect,
      scale,
      left: (rect.width - width) / 2,
      top: (rect.height - height) / 2,
      width,
      height,
    };
  }, [imageSize]);

  const renderDraft = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const dpr = window.devicePixelRatio || 1;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, canvas.width / dpr, canvas.height / dpr);
    if (!draft) return;

    ctx.strokeStyle = '#1677ff';
    ctx.fillStyle = 'rgba(22,119,255,0.10)';
    ctx.lineWidth = 2;
    ctx.setLineDash([8, 6]);

    if (draft.mode === 'line') {
      ctx.beginPath();
      ctx.moveTo(draft.x1, draft.y1);
      ctx.lineTo(draft.x2, draft.y2);
      ctx.stroke();
    } else {
      ctx.fillRect(draft.x, draft.y, draft.width, draft.height);
      ctx.strokeRect(draft.x, draft.y, draft.width, draft.height);
    }
  }, [draft]);

  const resizeCanvas = useCallback(() => {
    const shell = shellRef.current;
    const canvas = canvasRef.current;
    if (!shell || !canvas) return;
    const dpr = window.devicePixelRatio || 1;
    canvas.width = Math.max(1, Math.round(shell.clientWidth * dpr));
    canvas.height = Math.max(1, Math.round(shell.clientHeight * dpr));
    canvas.style.width = `${shell.clientWidth}px`;
    canvas.style.height = `${shell.clientHeight}px`;
    renderDraft();
  }, [renderDraft]);

  useEffect(() => {
    resizeCanvas();
    const observer = new ResizeObserver(resizeCanvas);
    if (shellRef.current) observer.observe(shellRef.current);
    return () => observer.disconnect();
  }, [resizeCanvas]);

  useEffect(() => {
    renderDraft();
  }, [renderDraft]);

  const getPoint = (event) => {
    const m = metrics();
    if (!m) return null;
    const rawX = event.clientX - m.rect.left;
    const rawY = event.clientY - m.rect.top;
    if (rawX < m.left || rawX > m.left + m.width || rawY < m.top || rawY > m.top + m.height) {
      return null;
    }
    return {
      x: Math.max(m.left, Math.min(m.left + m.width, rawX)),
      y: Math.max(m.top, Math.min(m.top + m.height, rawY)),
      m,
    };
  };

  const toImagePoint = ({ x, y, m }) => ({
    x: Math.round((x - m.left) / m.scale),
    y: Math.round((y - m.top) / m.scale),
  });

  const pointerDown = (event) => {
    if (!drawMode || !frameUrl) return;
    const point = getPoint(event);
    if (!point) return;
    event.currentTarget.setPointerCapture?.(event.pointerId);
    dragRef.current = point;
    if (drawMode === 'line') {
      setDraft({ mode: 'line', x1: point.x, y1: point.y, x2: point.x, y2: point.y });
    } else {
      setDraft({ mode: drawMode, x: point.x, y: point.y, width: 0, height: 0 });
    }
  };

  const pointerMove = (event) => {
    if (!dragRef.current || !drawMode) return;
    const point = getPoint(event);
    if (!point) return;
    const start = dragRef.current;
    if (drawMode === 'line') {
      setDraft({ mode: 'line', x1: start.x, y1: start.y, x2: point.x, y2: point.y });
      return;
    }
    setDraft({
      mode: drawMode,
      x: Math.min(start.x, point.x),
      y: Math.min(start.y, point.y),
      width: Math.abs(point.x - start.x),
      height: Math.abs(point.y - start.y),
    });
  };

  const pointerUp = (event) => {
    const start = dragRef.current;
    if (!start || !drawMode) return;
    const end = getPoint(event);
    dragRef.current = null;
    setDraft(null);
    if (!end) return;

    const p1 = toImagePoint(start);
    const p2 = toImagePoint(end);
    if (drawMode === 'line') {
      if (Math.hypot(p2.x - p1.x, p2.y - p1.y) < 10) return;
      onGeometry(drawMode, { x1: p1.x, y1: p1.y, x2: p2.x, y2: p2.y });
      return;
    }

    const rect = {
      x: Math.min(p1.x, p2.x),
      y: Math.min(p1.y, p2.y),
      width: Math.abs(p2.x - p1.x),
      height: Math.abs(p2.y - p1.y),
    };
    if (rect.width < 10 || rect.height < 10) return;
    onGeometry(drawMode, rect);
  };

  return (
    <section className="panel video-card">
      <div className="video-head">
        <span className="panel-title"><CameraIcon size={15} /> Live Camera</span>
        <span className="video-head-tools">
          <span className="resolution-tag">
            <ExpandIcon size={12} />
            {frameSize?.width || 640} × {frameSize?.height || 480}
          </span>
          {drawMode ? (
            <button
              type="button"
              className="button button-danger-outline button-small"
              onClick={onCancelDraw}
            >
              <StopIcon size={12} />
              Cancel
            </button>
          ) : null}
        </span>
      </div>

      <div
        ref={shellRef}
        className={`video-shell ${drawMode ? 'drawing' : ''}`}
        onPointerDown={pointerDown}
        onPointerMove={pointerMove}
        onPointerUp={pointerUp}
        onPointerCancel={() => {
          dragRef.current = null;
          setDraft(null);
        }}
      >
        {frameUrl ? (
          <img ref={imageRef} src={frameUrl} alt="Intel RealSense live stream" draggable={false} />
        ) : (
          <div className="camera-empty">
            <div className="camera-empty-icon"><CameraIcon size={26} /></div>
            <h3>No live camera frame</h3>
            <p>Connect a RealSense camera to start the WebSocket stream.</p>
          </div>
        )}
        <canvas ref={canvasRef} />

        <div className={`camera-guidance ${drawMode ? 'drawing' : setupComplete ? 'ready' : ''}`}>
          <span className="guidance-indicator"><CrosshairIcon size={13} /></span>
          <span className="guidance-text">{messageText}</span>
        </div>

        {drawMode ? (
          <div className="draw-mode-pill">
            <CrosshairIcon size={13} /> Drawing {drawMode === 'box' ? 'count box' : drawMode}
          </div>
        ) : null}
      </div>
    </section>
  );
}
