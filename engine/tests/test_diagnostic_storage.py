import gzip
from app.diagnostic_storage import compress_native_diagnostics


def test_internal_diagnostics_are_lossless_and_customer_results_stay_untouched(tmp_path):
    page=tmp_path/'native-detection'/'0'; page.mkdir(parents=True)
    raw=b'{"geometry":' + b'123456,'*10000 + b'0}'
    for name in ('result.json','detection-inputs.json'):
        (page/name).write_bytes(raw)
    other=tmp_path/'quantities.json'; other.write_bytes(b'{"metres":42}')
    assert compress_native_diagnostics(tmp_path)>0
    for name in ('result.json','detection-inputs.json'):
        assert not (page/name).exists()
        with gzip.open(page/(name+'.gz'),'rb') as stream: assert stream.read()==raw
    assert other.read_bytes()==b'{"metres":42}'
    assert compress_native_diagnostics(tmp_path)==0
