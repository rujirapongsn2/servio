"""Display labels from assigned catalog tables, matched to exact image bytes."""
import logging
import re

from sqlalchemy.exc import SQLAlchemyError


def catalog_labels(asset_ids: list[str], team_id: int | None) -> dict[str, dict[str, str]]:
    if team_id is None:
        return {}
    assets = {asset for asset in asset_ids if re.fullmatch(r'[a-f0-9]{64}', asset)}
    if not assets:
        return {}
    from app.knowledge_image_search import assigned_bundles
    from app.okf_service import OKFService

    service = OKFService()
    candidates: dict[str, list[dict[str, str]]] = {}
    try:
        bundle_ids = assigned_bundles(team_id)
    except SQLAlchemyError:
        logging.getLogger(__name__).warning('Catalog display labels unavailable')
        return {}
    for bundle_id in sorted(bundle_ids):
        try:
            for table in service.table_inventory(bundle_id, team_id):
                columns = {column['name'] for column in table['columns']}
                if not {'product_name', 'sha256'} <= columns:
                    continue
                fields = ['sha256', 'product_name', *[name for name in ('sku_or_color_code', 'brand') if name in columns]]
                # Assets are validated hex; identifiers come from the authorized schema.
                quote = lambda value: '"' + value.replace('"', '""') + '"'
                sql = ('SELECT ' + ','.join(map(quote, fields)) + ' FROM ' + quote(table['table_name'])
                       + ' WHERE "sha256" IN (' + ','.join("'" + asset + "'" for asset in sorted(assets)) + ')')
                result = service.query_tables(bundle_id, sql, team_id)
                if result['truncated']:
                    continue
                for values in result['rows']:
                    row = dict(zip(result['columns'], values))
                    name = row.get('product_name')
                    asset = row.get('sha256')
                    if asset not in assets or not isinstance(name, str) or not name.strip() or len(name) > 1000:
                        continue
                    label = {'title': name.strip()}
                    for source, target in [('sku_or_color_code', 'part_number'), ('brand', 'brand')]:
                        value = row.get(source)
                        if isinstance(value, (str, int)) and str(value).strip() and len(str(value)) <= 200:
                            label[target] = str(value).strip()
                    candidates.setdefault(asset, []).append(label)
        except (KeyError, ValueError, OSError, SQLAlchemyError):
            logging.getLogger(__name__).warning('Catalog display labels unavailable for bundle %s', bundle_id)
    # Conflicting catalogs cannot silently rename a product.
    return {asset: labels[0] for asset, labels in candidates.items() if all(label == labels[0] for label in labels)}
