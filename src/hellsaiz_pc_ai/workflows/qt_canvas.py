from __future__ import annotations

import math
from typing import Any

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsObject,
    QGraphicsPathItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
)

from hellsaiz_pc_ai.workflows.graph import GraphEdge, GraphNode, WorkflowGraph


class WorkflowNodeItem(QGraphicsObject):
    moved = Signal(str, float, float)
    WIDTH = 224.0
    HEIGHT = 86.0

    def __init__(self, node: GraphNode, x: float, y: float) -> None:
        super().__init__()
        self.node = node
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.setPos(x, y)
        self.setZValue(1)

    def boundingRect(self) -> QRectF:
        return QRectF(0.0, 0.0, self.WIDTH, self.HEIGHT)

    def _summary(self) -> str:
        cfg = self.node.config
        if self.node.kind == "trigger.text":
            return str(cfg.get("phrase", ""))
        if self.node.kind == "trigger.hotkey":
            return str(cfg.get("hotkey", ""))
        if self.node.kind == "condition.hour":
            return f"hour {cfg.get('operator')} {cfg.get('value')}"
        if self.node.kind == "action.tool":
            return str(cfg.get("name", ""))
        if self.node.kind == "action.wait":
            return f"wait {cfg.get('seconds')} sec"
        return ""

    def paint(self, painter: QPainter, option: Any, widget: Any = None) -> None:
        del option, widget
        selected = self.isSelected()
        border = QColor("#e8eaee") if selected else QColor("#747c88")
        fills = {
            "trigger.text": "#20252d",
            "trigger.hotkey": "#20252d",
            "condition.hour": "#252a32",
            "action.tool": "#171b21",
            "action.wait": "#171b21",
        }
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(QPen(border, 2.0 if selected else 1.2))
        painter.setBrush(QColor(fills.get(self.node.kind, "#171b21")))
        painter.drawRoundedRect(self.boundingRect(), 10.0, 10.0)
        painter.setPen(QColor("#f3f4f6"))
        painter.setFont(QFont("Segoe UI", 10, QFont.Weight.DemiBold))
        painter.drawText(
            QRectF(14, 10, self.WIDTH - 28, 24),
            Qt.AlignmentFlag.AlignLeft,
            self.node.id,
        )
        painter.setPen(QColor("#b7bec8"))
        painter.setFont(QFont("Segoe UI", 8, QFont.Weight.Medium))
        painter.drawText(
            QRectF(14, 37, self.WIDTH - 28, 18),
            Qt.AlignmentFlag.AlignLeft,
            self.node.kind.upper(),
        )
        painter.setPen(QColor("#8f98a5"))
        painter.setFont(QFont("Segoe UI", 8))
        painter.drawText(
            QRectF(14, 59, self.WIDTH - 28, 18),
            Qt.AlignmentFlag.AlignLeft,
            self._summary()[:38],
        )
        painter.setPen(QPen(QColor("#bbc1ca"), 1.0))
        painter.setBrush(QColor("#0c0e12"))
        painter.drawEllipse(QPointF(0, self.HEIGHT / 2), 4.5, 4.5)
        painter.drawEllipse(QPointF(self.WIDTH, self.HEIGHT / 2), 4.5, 4.5)

    def input_port(self) -> QPointF:
        return self.mapToScene(QPointF(0.0, self.HEIGHT / 2))

    def output_port(self) -> QPointF:
        return self.mapToScene(QPointF(self.WIDTH, self.HEIGHT / 2))

    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value: Any) -> Any:
        result = super().itemChange(change, value)
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            position = self.pos()
            self.moved.emit(self.node.id, position.x(), position.y())
        return result


class WorkflowCanvas(QGraphicsView):
    """Monochrome draggable workflow graph canvas with persisted node positions."""

    def __init__(self, parent: Any = None) -> None:
        scene = QGraphicsScene()
        super().__init__(scene, parent)
        self._scene_graph = scene
        self._graph: WorkflowGraph | None = None
        self._nodes: dict[str, WorkflowNodeItem] = {}
        self._connections: list[
            tuple[GraphEdge, QGraphicsPathItem, QGraphicsSimpleTextItem | None]
        ] = []
        self._zoom = 1.0
        self.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        self.setBackgroundBrush(QColor("#0b0d11"))
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.BoundingRectViewportUpdate)
        self.setMinimumWidth(360)

    def set_graph(
        self,
        graph: WorkflowGraph,
        positions: dict[str, dict[str, float]] | None = None,
    ) -> None:
        self._graph = graph
        self._scene_graph.clear()
        self._nodes.clear()
        self._connections.clear()
        positions = positions or {}
        for index, node in enumerate(graph.nodes):
            saved = positions.get(node.id, {})
            try:
                x = float(saved.get("x", (index % 3) * 300))
                y = float(saved.get("y", (index // 3) * 150))
                if not math.isfinite(x) or not math.isfinite(y):
                    raise ValueError
            except (AttributeError, TypeError, ValueError):
                x, y = (index % 3) * 300.0, (index // 3) * 150.0
            item = WorkflowNodeItem(node, x, y)
            self._scene_graph.addItem(item)
            self._nodes[node.id] = item

        for edge in graph.edges:
            path = QGraphicsPathItem()
            path.setZValue(-2)
            path.setPen(QPen(QColor("#77808c"), 2.0))
            self._scene_graph.addItem(path)
            label = None
            if edge.when:
                label = QGraphicsSimpleTextItem(edge.when.upper())
                label.setBrush(QColor("#d0d4da"))
                label.setFont(QFont("Segoe UI", 8, QFont.Weight.DemiBold))
                label.setZValue(-1)
                self._scene_graph.addItem(label)
            self._connections.append((edge, path, label))

        for item in self._nodes.values():
            item.moved.connect(self._node_moved)
        self._refresh_connections()
        self._update_scene_rect()

    def _node_moved(self, node_id: str, x: float, y: float) -> None:
        del x, y
        self._refresh_connections(node_id)
        self._update_scene_rect()

    def _refresh_connections(self, node_id: str | None = None) -> None:
        for edge, path_item, label_item in self._connections:
            if node_id is not None and node_id not in {edge.source, edge.target}:
                continue
            source = self._nodes.get(edge.source)
            target = self._nodes.get(edge.target)
            if source is None or target is None:
                continue
            start = source.output_port()
            end = target.input_port()
            span = max(70.0, abs(end.x() - start.x()) * 0.45)
            path = QPainterPath(start)
            path.cubicTo(
                start + QPointF(span, 0.0),
                end - QPointF(span, 0.0),
                end,
            )
            path_item.setPath(path)
            if label_item is not None:
                midpoint = path.pointAtPercent(0.5)
                label_item.setPos(midpoint.x() - 9, midpoint.y() - 18)

    def _update_scene_rect(self) -> None:
        rect = self._scene_graph.itemsBoundingRect()
        if rect.isNull():
            rect = QRectF(0, 0, 600, 400)
        self._scene_graph.setSceneRect(rect.adjusted(-90, -90, 90, 90))

    def export_layout(self) -> dict[str, dict[str, float]]:
        return {
            node_id: {"x": round(item.pos().x(), 2), "y": round(item.pos().y(), 2)}
            for node_id, item in self._nodes.items()
        }

    def reset_layout(self) -> None:
        if self._graph is not None:
            self.set_graph(self._graph, {})

    def fit_graph(self) -> None:
        rect = self._scene_graph.itemsBoundingRect()
        if not rect.isNull():
            self.fitInView(rect.adjusted(-45, -45, 45, 45), Qt.AspectRatioMode.KeepAspectRatio)
            self._zoom = self.transform().m11()

    def wheelEvent(self, event: Any) -> None:
        factor = 1.15 if event.angleDelta().y() > 0 else 0.87
        next_zoom = self._zoom * factor
        if 0.35 <= next_zoom <= 2.8:
            self.scale(factor, factor)
            self._zoom = next_zoom
            event.accept()
        else:
            event.ignore()

    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:
        super().drawBackground(painter, rect)
        step = 32
        left = math.floor(rect.left() / step) * step
        top = math.floor(rect.top() / step) * step
        painter.setPen(QPen(QColor("#171b21"), 1.0))
        x = left
        while x <= rect.right():
            painter.drawLine(x, int(rect.top()), x, int(rect.bottom()))
            x += step
        y = top
        while y <= rect.bottom():
            painter.drawLine(int(rect.left()), y, int(rect.right()), y)
            y += step
