import pytest
from allin1.weapon_preview_worker import stock_component_pair
from allin1 import prelaunch_previews as p
from allin1.stock_weapon_previews import file_state


def test_ebr_resolves_exact_stock_scope_pair():
    pair=[{'path':'weapons/w_at_scope_large.ydr'}, {'path':'weapons/w_at_scope_large.ytd'}]
    assert stock_component_pair({'stock_component_assets':{'w_at_scope_large':pair}},'w_at_scope_large')==pair


@pytest.mark.parametrize('pair',[None,[],[{'path':'wrong.ydr'},{'path':'scope.ytd'}],
                                 [{'path':'w_at_scope_large.ydr'},{'path':'scope.meta'}]])
def test_external_component_missing_or_mismatched_fails_closed(pair):
    with pytest.raises(ValueError):
        stock_component_pair({'stock_component_assets':{'w_at_scope_large':pair}},'w_at_scope_large')


def test_custom_preview_tracks_stock_dependency_changes(tmp_path):
    source=tmp_path/'custom.rpf';source.write_bytes(b'custom')
    stock=tmp_path/'stock.rpf';stock.write_bytes(b'stock')
    ref={'archive':'stock.rpf','state':file_state(stock)}
    item={'archive':'custom.rpf','archive_sha256':p.sha(source),'stock_component_assets':{'scope':[ref,ref]}}
    original=p.key_for(item,'Enhanced','renderer')
    assert p.source_unchanged(tmp_path,item)
    stock.write_bytes(b'changed')
    assert not p.source_unchanged(tmp_path,item)
    ref['state']=file_state(stock)
    assert p.key_for(item,'Enhanced','renderer')!=original
