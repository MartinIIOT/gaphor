'''
PackageItem diagram item
'''
# vim:sw=4:et

from __future__ import generators

import gobject
import pango
import diacanvas
import gaphor.UML as UML
from gaphor.diagram import initialize_item
from nameditem import NamedItem

class PackageItem(NamedItem):
    TAB_X=50
    TAB_Y=20
    MARGIN_X=60
    MARGIN_Y=30

    def __init__(self, id=None):
        NamedItem.__init__(self, id)
        self.set(height=50, width=100)
        self._border = diacanvas.shape.Path()
        self._border.set_line_width(2.0)

    def on_update(self, affine):
        # Center the text
        w, h = self.get_name_size()
        self.set(min_width=w + PackageItem.MARGIN_X,
                 min_height=h + PackageItem.MARGIN_Y)
        self.update_name(x=0, y=(self.height - h + PackageItem.TAB_Y) / 2,
                         width=self.width, height=h)

        NamedItem.on_update(self, affine)

        o = 0.0
        h = self.height
        w = self.width
        x = PackageItem.TAB_X
        y = PackageItem.TAB_Y
        line = ((x, y), (x, o), (o, o), (o, h), (w, h), (w, y), (o, y))
        self._border.line(line)
        self.expand_bounds(1.0)

    def on_shape_iter(self):
        yield self._border
        for s in NamedItem.on_shape_iter(self):
            yield s

initialize_item(PackageItem, UML.Package)
