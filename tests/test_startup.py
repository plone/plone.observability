from unittest import mock


class FakeEvent:
    pass


class TestOnProcessStarting:
    @mock.patch("plone.observability.startup._health_server")
    @mock.patch("plone.observability.startup.Zope2")
    @mock.patch("plone.observability.startup.queryUtility", return_value=None)
    def test_starts_health_server(self, mock_qu, mock_zope2, mock_server):
        from plone.observability.startup import on_process_starting

        mock_zope2.DB = mock.MagicMock()
        on_process_starting(FakeEvent())
        mock_server.start.assert_called_once()

    @mock.patch("plone.observability.startup._health_server")
    @mock.patch("plone.observability.startup.Zope2")
    @mock.patch("plone.observability.startup.queryUtility")
    def test_wires_db_to_health_server(self, mock_qu, mock_zope2, mock_server):
        from plone.observability.startup import on_process_starting

        fake_db = mock.MagicMock()
        mock_zope2.DB = fake_db
        mock_qu.return_value = None
        on_process_starting(FakeEvent())
        assert mock_server.db == fake_db

    @mock.patch("plone.observability.startup._health_server")
    @mock.patch("plone.observability.startup.Zope2")
    @mock.patch("plone.observability.startup.queryUtility")
    def test_wires_db_to_readiness_check(self, mock_qu, mock_zope2, mock_server):
        from plone.observability.startup import on_process_starting

        fake_db = mock.MagicMock()
        mock_zope2.DB = fake_db
        fake_check = mock.MagicMock()
        mock_qu.return_value = fake_check
        on_process_starting(FakeEvent())
        assert fake_check.db == fake_db
