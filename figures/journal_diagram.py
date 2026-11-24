"""Minimal vector primitives for compact journal diagrams.

The module deliberately avoids presentation-slide conventions: no title bars,
no shadowed cards, and no decorative panels.  Icons identify semantic objects;
position, shape and edge style carry the structure.  All coordinates use a
page-like top-left origin so layouts are easy to audit against manuscript
column widths.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import atan2, cos, sin, pi
from pathlib import Path
from typing import Iterable, Sequence

from reportlab.lib.colors import Color
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfgen.canvas import Canvas

from figure_typography import (
    ACCENT, GRID, GUIDE, INK, LIGHT, NEGATIVE, PALE_BLUE, PALE_GREEN,
    PALE_ORANGE, POSITIVE, SECONDARY, WHITE, register_fonts,
)


@dataclass(frozen=True)
class Bounds:
    x: float
    y: float
    w: float
    h: float

    @property
    def right(self) -> float:
        return self.x + self.w

    @property
    def bottom(self) -> float:
        return self.y + self.h

    def overlaps(self, other: "Bounds", gap: float = 0) -> bool:
        return (self.x < other.right + gap and other.x < self.right + gap and
                self.y < other.bottom + gap and other.y < self.bottom + gap)


class JournalCanvas:
    """Vector canvas with stable typography and lightweight clearance checks."""

    def __init__(self, path: Path, width: float, height: float, title: str):
        register_fonts()
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.width = width
        self.height = height
        self.c = Canvas(str(path), pagesize=(width, height), invariant=True,
                        initialFontName="Body")
        self.c.setTitle(title)
        self.c.setCreator("")
        self.text_boxes: list[tuple[Bounds, str]] = []

    def _py(self, y: float) -> float:
        return self.height - y

    def text(self, x: float, y: float, value: str, *, font: str = "Body",
             size: float = 10.0, color=INK, align: str = "center",
             track: bool = True) -> Bounds:
        value = str(value)
        width = pdfmetrics.stringWidth(value, font, size)
        left = x - {"left": 0, "center": width / 2, "right": width}[align]
        box = Bounds(left, y - size * .76, width, size * 1.05)
        if left < 2 or box.right > self.width - 2 or box.y < 1 or box.bottom > self.height - 1:
            raise ValueError(f"text outside figure: {value!r} at {box}")
        if track:
            self.text_boxes.append((box, value))
        self.c.setFont(font, size)
        self.c.setFillColor(color)
        draw = {"left": self.c.drawString, "center": self.c.drawCentredString,
                "right": self.c.drawRightString}[align]
        draw(x, self._py(y), value)
        return box

    def multi(self, x: float, y: float, lines: Sequence[str], *, font="Body",
              size=9.6, leading=11.0, color=INK, align="center") -> list[Bounds]:
        return [self.text(x, y + i * leading, line, font=font, size=size,
                          color=color, align=align)
                for i, line in enumerate(lines)]

    def line(self, x1: float, y1: float, x2: float, y2: float, *,
             color=INK, width=.9, dash: Sequence[float] | None = None) -> None:
        self.c.saveState()
        self.c.setStrokeColor(color)
        self.c.setLineWidth(width)
        if dash:
            self.c.setDash(*dash)
        self.c.line(x1, self._py(y1), x2, self._py(y2))
        self.c.restoreState()

    def polyline(self, points: Sequence[tuple[float, float]], *, color=INK,
                 width=.9, dash: Sequence[float] | None = None) -> None:
        if len(points) < 2:
            raise ValueError("polyline needs at least two points")
        self.c.saveState()
        self.c.setStrokeColor(color)
        self.c.setLineWidth(width)
        if dash:
            self.c.setDash(*dash)
        p = self.c.beginPath()
        p.moveTo(points[0][0], self._py(points[0][1]))
        for x, y in points[1:]:
            p.lineTo(x, self._py(y))
        self.c.drawPath(p, fill=0, stroke=1)
        self.c.restoreState()

    def arrow(self, points: Sequence[tuple[float, float]], *, color=INK,
              width=1.0, dash: Sequence[float] | None = None,
              head=4.5) -> None:
        if len(points) < 2:
            raise ValueError("arrow needs at least two points")
        self.polyline(points, color=color, width=width, dash=dash)
        (x0, y0), (x1, y1) = points[-2:]
        angle = atan2(y1 - y0, x1 - x0)
        left = (x1 - head * cos(angle) + head * .48 * sin(angle),
                y1 - head * sin(angle) - head * .48 * cos(angle))
        right = (x1 - head * cos(angle) - head * .48 * sin(angle),
                 y1 - head * sin(angle) + head * .48 * cos(angle))
        self.c.saveState()
        self.c.setFillColor(color)
        p = self.c.beginPath()
        p.moveTo(x1, self._py(y1))
        p.lineTo(left[0], self._py(left[1]))
        p.lineTo(right[0], self._py(right[1]))
        p.close()
        self.c.drawPath(p, fill=1, stroke=0)
        self.c.restoreState()

    def circle(self, x: float, y: float, r: float, *, stroke=INK,
               fill=WHITE, width=.9, dash: Sequence[float] | None = None) -> None:
        self.c.saveState()
        self.c.setLineWidth(width)
        self.c.setStrokeColor(stroke)
        self.c.setFillColor(fill)
        if dash:
            self.c.setDash(*dash)
        self.c.circle(x, self._py(y), r, fill=1, stroke=1)
        self.c.restoreState()

    def rect(self, x: float, y: float, w: float, h: float, *, stroke=INK,
             fill=WHITE, width=.8, radius=0, dash: Sequence[float] | None = None) -> None:
        self.c.saveState()
        self.c.setLineWidth(width)
        self.c.setStrokeColor(stroke)
        self.c.setFillColor(fill)
        if dash:
            self.c.setDash(*dash)
        if radius:
            self.c.roundRect(x, self._py(y + h), w, h, radius, fill=1, stroke=1)
        else:
            self.c.rect(x, self._py(y + h), w, h, fill=1, stroke=1)
        self.c.restoreState()

    def bracket(self, x: float, y1: float, y2: float, *, side="right",
                color=SECONDARY, width=.9, arm=5) -> None:
        sign = 1 if side == "right" else -1
        self.polyline([(x + sign * arm, y1), (x, y1), (x, y2),
                       (x + sign * arm, y2)], color=color, width=width)

    def status(self, x: float, y: float, ok: bool, *, radius=6.2) -> None:
        color = POSITIVE if ok else NEGATIVE
        self.circle(x, y, radius, stroke=color, fill=color, width=.6)
        self.c.saveState()
        self.c.setStrokeColor(WHITE)
        self.c.setLineWidth(1.5)
        if ok:
            self.polyline([(x - 3.0, y), (x - .7, y + 2.4),
                           (x + 3.5, y - 2.5)], color=WHITE, width=1.5)
        else:
            self.line(x - 2.7, y - 2.7, x + 2.7, y + 2.7, color=WHITE, width=1.4)
            self.line(x - 2.7, y + 2.7, x + 2.7, y - 2.7, color=WHITE, width=1.4)
        self.c.restoreState()

    def icon(self, x: float, y: float, kind: str, size: float = 16,
             *, color=ACCENT, fill=WHITE) -> None:
        """Draw a compact original line icon.  No external artwork is used."""
        c = self.c
        s = size
        c.saveState()
        c.translate(x, self._py(y))
        c.setStrokeColor(color)
        c.setFillColor(fill)
        c.setLineWidth(max(.75, s * .055))
        if kind == "person":
            c.circle(0, s * .22, s * .20, fill=0, stroke=1)
            p = c.beginPath(); p.moveTo(-s*.34, -s*.43)
            p.curveTo(-s*.32, -s*.08, s*.32, -s*.08, s*.34, -s*.43)
            c.drawPath(p, fill=0, stroke=1)
        elif kind == "document":
            p = c.beginPath(); p.moveTo(-s*.32, -s*.42); p.lineTo(s*.32, -s*.42)
            p.lineTo(s*.32, s*.20); p.lineTo(s*.12, s*.42); p.lineTo(-s*.32, s*.42); p.close()
            c.drawPath(p, fill=1, stroke=1); c.line(s*.12, s*.42, s*.12, s*.20); c.line(s*.12, s*.20, s*.32, s*.20)
            for yy, ww in ((.08,.34),(-.08,.34),(-.24,.24)):
                c.line(-s*.20, s*yy, -s*.20+s*ww, s*yy)
        elif kind == "target":
            for rr in (.38,.24,.08): c.circle(0,0,s*rr,fill=0,stroke=1)
            c.line(s*.08,s*.08,s*.43,s*.43); c.line(s*.43,s*.43,s*.26,s*.41); c.line(s*.43,s*.43,s*.41,s*.26)
        elif kind == "family":
            for xx, yy in ((0,.22),(-.28,-.05),(.28,-.05)):
                c.circle(s*xx,s*yy,s*.11,fill=0,stroke=1)
            c.line(0,s*.10,0,-s*.16); c.line(-s*.28,-s*.16,s*.28,-s*.16)
            c.line(-s*.28,-s*.16,-s*.28,-s*.24); c.line(s*.28,-s*.16,s*.28,-s*.24)
        elif kind == "graph":
            pts=((-s*.30,-s*.22),(0,s*.29),(s*.30,-s*.22))
            for a,b in ((0,1),(1,2)): c.line(pts[a][0],pts[a][1],pts[b][0],pts[b][1])
            for xx,yy in pts: c.circle(xx,yy,s*.105,fill=1,stroke=1)
        elif kind == "layers":
            for offset in (-.18,0,.18):
                p=c.beginPath();p.moveTo(0,s*(.30+offset));p.lineTo(s*.34,s*(.10+offset));p.lineTo(0,s*(-.10+offset));p.lineTo(-s*.34,s*(.10+offset));p.close();c.drawPath(p,fill=0,stroke=1)
        elif kind == "database":
            c.ellipse(-s*.34,s*.18,s*.34,s*.40,fill=1,stroke=1)
            c.rect(-s*.34,-s*.30,s*.68,s*.60,fill=1,stroke=0)
            c.line(-s*.34,s*.29,-s*.34,-s*.30);c.line(s*.34,s*.29,s*.34,-s*.30)
            c.arc(-s*.34,-s*.02,s*.34,s*.20,180,180);c.arc(-s*.34,-s*.20,s*.34,s*.02,180,180);c.arc(-s*.34,-s*.40,s*.34,-s*.18,180,180)
        elif kind == "profile":
            c.roundRect(-s*.34,-s*.40,s*.68,s*.80,s*.05,fill=1,stroke=1)
            for yy in (.20,0,-.20):
                c.circle(-s*.20,s*yy,s*.035,fill=1,stroke=1); c.line(-s*.10,s*yy,s*.20,s*yy)
        elif kind == "key":
            c.circle(-s*.20,s*.12,s*.18,fill=0,stroke=1);c.line(-s*.03,s*.01,s*.36,-s*.38);c.line(s*.18,-s*.20,s*.28,-s*.10)
        elif kind == "object":
            p=c.beginPath();p.moveTo(0,s*.38);p.lineTo(s*.34,s*.17);p.lineTo(s*.34,-s*.25);p.lineTo(0,-s*.42);p.lineTo(-s*.34,-s*.25);p.lineTo(-s*.34,s*.17);p.close();c.drawPath(p,fill=1,stroke=1)
            c.line(0,s*.38,0,-s*.42);c.line(-s*.34,s*.17,0,-s*.04);c.line(s*.34,s*.17,0,-s*.04)
        elif kind == "serializer":
            c.roundRect(-s*.34,-s*.38,s*.68,s*.76,s*.05,fill=1,stroke=1)
            c.line(-s*.20,s*.18,s*.20,s*.18);c.line(-s*.20,0,s*.08,0);c.line(-s*.20,-s*.18,s*.20,-s*.18)
        elif kind == "clock":
            c.circle(0,0,s*.36,fill=0,stroke=1);c.line(0,0,0,s*.20);c.line(0,0,s*.18,-s*.10)
        elif kind == "check":
            c.circle(0,0,s*.38,fill=0,stroke=1);c.line(-s*.18,0,-s*.04,-s*.16);c.line(-s*.04,-s*.16,s*.22,s*.18)
        elif kind == "cross":
            c.circle(0,0,s*.38,fill=0,stroke=1);c.line(-s*.18,-s*.18,s*.18,s*.18);c.line(-s*.18,s*.18,s*.18,-s*.18)
        elif kind == "state":
            c.circle(0,0,s*.34,fill=1,stroke=1)
        else:
            c.restoreState(); raise ValueError(f"unknown icon: {kind}")
        c.restoreState()

    def finish(self) -> Path:
        self.c.showPage()
        self.c.save()
        return self.path


def export_svg(pdf: Path, svg: Path) -> None:
    import fitz
    svg.parent.mkdir(parents=True, exist_ok=True)
    with fitz.open(pdf) as doc:
        svg.write_text(doc[0].get_svg_image(text_as_path=False), encoding="utf-8")
