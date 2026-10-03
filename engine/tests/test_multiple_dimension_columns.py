from types import SimpleNamespace as NS
from vvs_engine.semantics.annotation import _find_dn


def block(last_y=16):
    return NS(height=10, rows=[
        NS(role='designation',line=NS(bbox=(0,0,150,10))),
        NS(role='dn',line=NS(bbox=(5,16,15,26)),text_norm='16'),
        NS(role='dn',line=NS(bbox=(55,16,65,26)),text_norm='75'),
        NS(role='dn',line=NS(bbox=(105,last_y,115,last_y+10)),text_norm='22')])


def test_each_of_three_codes_reads_its_own_printed_dimension_column():
    b=block()
    for x,dn in [(0,16),(50,75),(100,22)]:
        found=_find_dn('KV1-X31',['KV1','X31'],None,b,0,(x,0,x+40,10))
        assert found[0]==dn and found[1]=='row'


def test_extra_columns_do_not_capture_distant_numbers():
    assert _find_dn('KV1-X31',['KV1','X31'],None,block(80),0,(100,0,140,10))[0] is None


def test_a_code_does_not_take_the_size_printed_under_its_neighbour():
    # `S3-R8  5xVV1-X31` written as two rows on one baseline, over `75  16`: VV1 is 16, not S3-R8's 75
    b=NS(height=6,rows=[
        NS(role='designation',line=NS(bbox=(1132,718,1157,724))),
        NS(role='designation',line=NS(bbox=(1167,719,1211,725))),
        NS(role='dn',line=NS(bbox=(1137,728,1150,735)),text_norm='75'),
        NS(role='dn',line=NS(bbox=(1182,728,1192,735)),text_norm='16')])
    assert _find_dn('VV1-X31',['VV1','X31'],None,b,1)[0]==16
    assert _find_dn('S3-R8',['S3','R8'],None,b,0)[0]==75


def test_a_size_row_under_its_code_is_still_read():
    b=NS(height=6,rows=[NS(role='designation',line=NS(bbox=(0,0,40,6))),
                        NS(role='dn',line=NS(bbox=(14,9,24,15)),text_norm='15')])
    assert _find_dn('KV1-R1',['KV1','R1'],None,b,0)[:2]==(15,'row')
