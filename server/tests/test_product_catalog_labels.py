import pytest

from app.product_catalog_labels import catalog_labels


@pytest.fixture
def catalog(monkeypatch):
    from app import knowledge_image_search, okf_service
    asset = 'a' * 64
    rows = [[asset, 'Sleigh Creek™ Landau SK35', 'SK35', 'Daltile']]
    monkeypatch.setattr(knowledge_image_search, 'assigned_bundles', lambda team: {25} if team == 26 else set())
    monkeypatch.setattr(okf_service.OKFService, 'table_inventory', lambda self, bundle, team: [
        {'table_name': 'data_1', 'columns': [{'name': key} for key in ['sha256', 'product_name', 'sku_or_color_code', 'brand']]}])
    def query(self, bundle, sql, team):
        assert team == 26 and bundle == 25
        assert asset in sql
        return {'columns': ['sha256', 'product_name', 'sku_or_color_code', 'brand'], 'rows': rows, 'truncated': False}
    monkeypatch.setattr(okf_service.OKFService, 'query_tables', query)
    return asset, rows


def test_exact_image_bytes_receive_manifest_name_and_code(catalog):
    asset, _ = catalog
    assert catalog_labels([asset], 26) == {asset: {'title': 'Sleigh Creek™ Landau SK35', 'part_number': 'SK35', 'brand': 'Daltile'}}


def test_conflicting_or_unmatched_catalog_rows_do_not_rename_images(catalog):
    asset, rows = catalog
    rows.append([asset, 'Different product', 'OTHER', 'Daltile'])
    rows.append(['b' * 64, 'Unrelated image', 'OTHER', 'Daltile'])
    assert catalog_labels([asset], 26) == {}


def test_no_catalog_access_returns_no_labels(catalog):
    asset, _ = catalog
    assert catalog_labels([asset], 99) == {}
    assert catalog_labels([asset], None) == {}
    assert catalog_labels(["'; DROP TABLE data_1;--"], 26) == {}
