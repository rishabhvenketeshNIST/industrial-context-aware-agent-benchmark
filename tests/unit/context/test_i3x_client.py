from unittest.mock import Mock

from icab.context.i3x.client import I3XClient


def test_i3x_client_delegates_get_info():
    client = I3XClient.__new__(I3XClient)
    client.client = Mock()

    expected = Mock()
    client.client.get_info.return_value = expected

    result = client.get_info()

    assert result is expected
    client.client.get_info.assert_called_once_with()
