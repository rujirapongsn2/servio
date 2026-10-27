"""Keep product subtotals independent of the complete table total."""
import json

from app import agent_config
from app.knowledge_table_editor import SaveEditableWorkbook
from test_knowledge_images import store
from test_queryable_knowledge import tabular, upload, invoke


def test_agent_receives_distinct_thai_total_scopes(tabular):
    bundle = upload(tabular, queryable=True)
    tool = agent_config.create_okf_knowledge_graph_tool(
        'sales', {'okf_bundle_id': bundle['id'], 'queryable': True}, runtime_team_agent_id=1)
    # These are user-facing scope terms the Agent must distinguish, not SQL names.
    for term in ('ยอดเฉพาะสินค้า', 'ยอดรวมทั้งตาราง', 'ยอดรวมสินค้าทั้งหมด'):
        assert term in tool.description, f'Agent lacks total-scope guidance for {term}'
    assert 'independent' in tool.description
    assert 'date' in tool.description and 'branch' in tool.description
    assert 'clarify' in tool.description
    assert 'exact stored product name' in tool.description
    assert 'zero matches' in tool.description


def test_one_agent_can_return_product_and_table_totals_after_edit(tabular):
    service, _, _ = tabular
    bundle = upload(tabular, queryable=True)
    tool = agent_config.create_okf_knowledge_graph_tool(
        'sales', {'okf_bundle_id': bundle['id'], 'queryable': True}, runtime_team_agent_id=1)
    sql = '''SELECT SUM(CASE WHEN "สินค้า" = 'โต๊ะ' THEN "จำนวน" * "ราคา" ELSE 0 END)
        AS product_subtotal, SUM("จำนวน" * "ราคา") AS table_total FROM data_1'''
    assert json.loads(invoke(tool, query='ยอดโต๊ะและยอดรวมทั้งตาราง', sql=sql))['rows'] == [[4500, 6000]]
    draft = service.editable_tables(bundle['id'], 1)
    draft['tables'][0]['rows'][0][2] = '7'
    service.save_editable_tables(bundle['id'], 1, SaveEditableWorkbook(
        expected_revision=draft['revision'], tables=draft['tables']))
    assert json.loads(invoke(tool, query='ยอดโต๊ะและยอดรวมทั้งตารางล่าสุด', sql=sql))['rows'] == [[12000, 13500]]


def test_product_only_total_does_not_include_other_products(tabular):
    bundle = upload(tabular, queryable=True)
    tool = agent_config.create_okf_knowledge_graph_tool(
        'sales', {'okf_bundle_id': bundle['id'], 'queryable': True}, runtime_team_agent_id=1)
    result = json.loads(invoke(tool, query='เฉพาะเก้าอี้',
        sql='SELECT SUM("จำนวน" * "ราคา") FROM data_1 WHERE "สินค้า" = \'เก้าอี้\''))
    assert result['rows'] == [[1500]]


def test_full_product_name_and_unmatched_name_have_different_meanings(tabular):
    service, _, _ = tabular
    bundle = upload(tabular, queryable=True)
    draft = service.editable_tables(bundle['id'], 1)
    draft['tables'][0]['rows'][0][1] = 'โต๊ะ Excel'
    service.save_editable_tables(bundle['id'], 1, SaveEditableWorkbook(
        expected_revision=draft['revision'], tables=draft['tables']))
    tool = agent_config.create_okf_knowledge_graph_tool(
        'sales', {'okf_bundle_id': bundle['id'], 'queryable': True}, runtime_team_agent_id=1)
    result = json.loads(invoke(tool, query='ยอดเฉพาะโต๊ะ Excel', sql='''SELECT COUNT(*),
        SUM("จำนวน" * "ราคา") FROM data_1 WHERE "สินค้า" = 'โต๊ะ Excel' '''))
    assert result['rows'] == [[1, 3000]]
    missing = json.loads(invoke(tool, query='ยอดเฉพาะชื่อที่ไม่มี', sql='''SELECT COUNT(*),
        SUM("จำนวน" * "ราคา") FROM data_1 WHERE "สินค้า" = 'ไม่มีสินค้านี้' '''))
    assert missing['rows'] == [[0, None]]
