from icab.context.uns.models import UNSNode
from icab.context.uns.repository import InMemoryUNSRepository


def test_uns_browse_returns_direct_children():
    repository = InMemoryUNSRepository(
        [
            UNSNode(
                path="site/tep",
                display_name="TEP",
                node_type="site",
            ),
            UNSNode(
                path="site/tep/reaction",
                display_name="Reaction",
                node_type="area",
            ),
            UNSNode(
                path="site/tep/reaction/reactor",
                display_name="Reactor",
                node_type="equipment",
            ),
            UNSNode(
                path="site/tep/reaction/condenser",
                display_name="Condenser",
                node_type="equipment",
            ),
        ]
    )

    children = repository.browse("site/tep/reaction")

    assert [node.path for node in children] == [
        "site/tep/reaction/condenser",
        "site/tep/reaction/reactor",
    ]


def test_uns_read_returns_node():
    node = UNSNode(
        path="site/tep/reaction/reactor",
        display_name="Reactor",
        node_type="equipment",
        canonical_id="urn:icab:equipment:reactor",
    )
    repository = InMemoryUNSRepository([node])

    result = repository.read("site/tep/reaction/reactor")

    assert result == node


def test_uns_read_unknown_path_returns_none():
    repository = InMemoryUNSRepository()

    assert repository.read("site/tep/unknown") is None
