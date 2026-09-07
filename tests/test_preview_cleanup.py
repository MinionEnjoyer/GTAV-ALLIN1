import hashlib
import json
import re
from allin1 import prelaunch_previews as p


def test_orphan_cleanup_preserves_live_modified_and_unrelated(tmp_path):
    public=tmp_path/'images';public.mkdir()
    cache=tmp_path/'cache';cache.mkdir()
    names=[]
    for n in range(3):
        key=str(n)*64
        data=b'original'+bytes([n]);name='weapon_test.'+key+'.png'
        (public/name).write_bytes(data)
        (cache/(key+'.json')).write_text(json.dumps({'key':key,'sha256':hashlib.sha256(data).hexdigest()}))
        names.append(name)
    (public/names[2]).write_bytes(b'user edited')
    (public/'personal.png').write_bytes(b'untouched')
    (public/('weapon_unknown.'+'f'*64+'.png')).write_bytes(b'no ownership record')
    count=p.prune_published(public,cache,{'weapon_test':names[0]},p.NAME)
    assert count==1
    assert (public/names[0]).exists() and not (public/names[1]).exists()
    assert (public/names[2]).read_bytes()==b'user edited'
    assert (public/'personal.png').exists()
    assert len(list(public.glob('*.png')))==4


def test_recorded_digest_cleans_evicted_cache_image(tmp_path):
    public=tmp_path/'images';public.mkdir()
    name='apc.'+'a'*64+'.png';data=b'obsolete render'
    (public/name).write_bytes(data)
    assert p.prune_published(public,tmp_path/'absent',{},re.compile('[a-z0-9]+'),
        {name:hashlib.sha256(data).hexdigest()})==1


def test_digest_does_not_allow_path_escape(tmp_path):
    public=tmp_path/'images';public.mkdir()
    outside=tmp_path/'outside.png';outside.write_bytes(b'protected')
    assert p.prune_published(public,tmp_path/'absent',{},p.NAME,
        {'../outside.png':hashlib.sha256(b'protected').hexdigest()})==0
    assert outside.exists()
