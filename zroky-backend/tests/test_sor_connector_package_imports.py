from app.services.connectors.sor.config import (
    LEDGER_REFUND_CONNECTOR_TYPE as packaged_ledger_refund_type,
)
from app.services.connectors.sor.config import get_connector_config as packaged_get_config
from app.services.connectors.sor.http_base import (
    HttpJsonRecordConnector as packaged_http_connector,
)
from app.services.connectors.sor.runtime import (
    GenericRestApiConnector as packaged_generic_rest_connector,
)
from app.services.system_of_record_connector_config import (
    LEDGER_REFUND_CONNECTOR_TYPE as legacy_ledger_refund_type,
)
from app.services.system_of_record_connector_config import get_connector_config as legacy_get_config
from app.services.system_of_record_connectors import (
    GenericRestApiConnector as legacy_generic_rest_connector,
)
from app.services._sor_connectors_http_base import (
    HttpJsonRecordConnector as shim_http_connector,
)


def test_sor_connector_package_keeps_legacy_facades_stable() -> None:
    assert packaged_generic_rest_connector is legacy_generic_rest_connector
    assert packaged_http_connector is shim_http_connector
    assert packaged_get_config is legacy_get_config
    assert packaged_ledger_refund_type == legacy_ledger_refund_type == "ledger_refund_api"
