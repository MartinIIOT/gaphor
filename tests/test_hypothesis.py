"""A Property-based test."""

import itertools
import os
from io import StringIO

from hypothesis import assume, settings
from hypothesis.stateful import RuleBasedStateMachine, initialize, invariant, rule
from hypothesis.strategies import data, lists, sampled_from

from gaphor import UML
from gaphor.application import Session
from gaphor.core import Transaction
from gaphor.core.modeling import Diagram, ElementFactory, StyleSheet
from gaphor.core.modeling.element import generate_id, uuid_generator
from gaphor.diagram.tests.fixtures import allow, connect, disconnect
from gaphor.storage import storage
from gaphor.storage.xmlwriter import XMLWriter
from gaphor.ui.filemanager import load_default_model
from gaphor.UML import diagramitems
from gaphor.UML.classes.dependency import DependencyItem


class ModelConsistency(RuleBasedStateMachine):
    @property
    def model(self) -> ElementFactory:
        return self.session.get_service("element_factory")  # type: ignore[no-any-return]

    @property
    def transaction(self) -> Transaction:
        return Transaction(self.session.get_service("event_manager"))

    def select(self, predicate):
        elements = ordered(self.model.select(predicate))
        assume(elements)
        return sampled_from(elements)

    def diagrams(self):
        return self.select(lambda e: isinstance(e, Diagram))

    def relations(self, diagram):
        relations = [
            p
            for p in diagram.presentation
            if isinstance(p, diagramitems.DependencyItem)
        ]
        assume(relations)
        return sampled_from(ordered(relations))

    def targets(self, relation, handle):
        return self.select(
            lambda e: isinstance(e, diagramitems.ClassItem)
            and e.diagram is relation.diagram
            and allow(relation, handle, e)
        )

    @initialize()
    def new_session(self):
        generate_id(map(str, itertools.count()))
        self.session = Session()

        load_default_model(self.model)

        copy_service = self.session.get_service("copy")
        copy_service.clear()

    def teardown(self):
        generate_id(uuid_generator())

    def create_diagram(self):
        with self.transaction:
            return self.model.create(Diagram)

    @rule(data=data())
    def create_class(self, data):
        diagram = data.draw(self.diagrams())
        with self.transaction:
            diagram.create(diagramitems.ClassItem, subject=self.model.create(UML.Class))

    @rule(data=data())
    def create_dependency(self, data):
        diagram = data.draw(self.diagrams())
        with self.transaction:
            relation = diagram.create(diagramitems.DependencyItem)
        self._connect_relation(data, relation, relation.head)
        self._connect_relation(data, relation, relation.tail)

    @rule(data=data())
    def delete_element(self, data):
        elements = self.select(
            lambda e: not isinstance(e, (Diagram, StyleSheet, UML.Package))
        )
        element = data.draw(elements)
        with self.transaction:
            element.unlink()

    @rule(data=data())
    def connect_relation(self, data):
        diagram = data.draw(self.diagrams())
        relation = data.draw(self.relations(diagram))
        handle = data.draw(sampled_from([relation.head, relation.tail]))
        self._connect_relation(data, relation, handle)

    def _connect_relation(self, data, relation, handle):
        target = data.draw(self.targets(relation, handle))
        with self.transaction:
            connect(relation, handle, target)

    @rule(data=data())
    def disconnect_relation(self, data):
        diagram = data.draw(self.diagrams())
        relation = data.draw(self.relations(diagram))
        handle = data.draw(sampled_from([relation.head, relation.tail]))
        with self.transaction:
            disconnect(relation, handle)

    @rule()
    def undo(self):
        undo_manager = self.session.get_service("undo_manager")
        assume(undo_manager.can_undo())
        undo_manager.undo_transaction()

    @rule()
    def redo(self):
        undo_manager = self.session.get_service("undo_manager")
        assume(undo_manager.can_redo())
        undo_manager.redo_transaction()

    @rule(data=data())
    def copy(self, data):
        diagram = data.draw(self.diagrams())
        assume(diagram.ownedPresentation)
        copy_service = self.session.get_service("copy")
        # Take from model, to ensure order.
        items = data.draw(
            lists(
                sampled_from(ordered(diagram.ownedPresentation)),
                min_size=1,
                unique=True,
            )
        )
        copy_service.copy(items)

    @rule(data=data())
    def paste_link(self, data):
        copy_service = self.session.get_service("copy")
        assume(copy_service.can_paste())
        diagram = data.draw(self.diagrams())
        copy_service.paste_link(diagram)

    @rule(data=data())
    def paste_full(self, data):
        copy_service = self.session.get_service("copy")
        assume(copy_service.can_paste())
        diagram = data.draw(self.diagrams())
        copy_service.paste_full(diagram)

    @invariant()
    def check_relations(self):
        relation: DependencyItem
        for relation in self.model.select(diagramitems.DependencyItem):  # type: ignore[assignment]
            subject = relation.subject
            diagram = relation.diagram
            head = get_connected(diagram, relation.head)
            tail = get_connected(diagram, relation.tail)

            if head and tail:
                assert subject
                assert subject.supplier is head.subject
                assert subject.client is tail.subject
            else:
                assert not subject

    @invariant()
    def can_save_and_load(self):
        new_model = ElementFactory()
        with StringIO() as buffer:
            storage.save(XMLWriter(buffer), self.model)
            buffer.seek(0)
            storage.load(
                buffer,
                factory=new_model,
                modeling_language=self.session.get_service("modeling_language"),
            )

        assert (
            new_model.size() == self.model.size()
        ), f"{new_model.lselect()} != {self.model.lselect()}"


ModelConsistencyTestCase = ModelConsistency.TestCase


def get_connected(diagram, handle):
    """Get item connected to a handle."""
    cinfo = diagram.connections.get_connection(handle)
    if cinfo:
        return cinfo.connected
    return None


def ordered(elements):
    return sorted(elements, key=lambda e: e.id)  # type: ignore[no-any-return]


settings.register_profile("test", derandomize=True, max_examples=50)
settings.register_profile("ci", max_examples=500)
settings.load_profile("ci" if "CI" in os.environ else "test")
