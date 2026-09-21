import threading
import numpy as np
import pipe_types as pt


def test_parallel_ocr_preserves_order_failures_and_main_thread_geometry(monkeypatch):
    monkeypatch.setenv('PIPE_OCR_WORKERS', '4')
    barrier = threading.Barrier(4, timeout=5)
    caller = threading.get_ident()
    threads = set()

    def recognize(img, config, output_type):
        threads.add(threading.get_ident())
        barrier.wait()
        if img[0, 0] == 1 and '--psm 6 ' in config:
            raise RuntimeError('one failed pass')
        return {'variant': (int(img[0, 0]), config.split()[1])}

    def parse(*args, data, **kwargs):
        assert threading.get_ident() == caller
        return data['variant']

    monkeypatch.setattr(pt.pytesseract, 'image_to_data', recognize)
    monkeypatch.setattr(pt, '_ocr_word_rows', parse)
    got = list(pt._ocr_variants((np.zeros((2, 2)), np.ones((2, 2))), 4, (0, 0), 'x', None))
    assert len(threads) == 4
    assert got == [(0, '6'), (0, '11'), (1, '11')]


def test_serial_ocr_stays_on_caller(monkeypatch):
    monkeypatch.setenv('PIPE_OCR_WORKERS', '1')
    caller = threading.get_ident()
    def recognize(*args, **kwargs):
        assert threading.get_ident() == caller
        return {'ok': True}
    monkeypatch.setattr(pt.pytesseract, 'image_to_data', recognize)
    monkeypatch.setattr(pt, '_ocr_word_rows', lambda *args, **kwargs: ['read'])
    assert list(pt._ocr_variants((None, None), 4, (0, 0), 'x', None)) == [['read']] * 4


def test_eight_workers_span_scales_and_keep_coordinate_mapping(monkeypatch):
    monkeypatch.setenv('PIPE_OCR_WORKERS', '8')
    barrier = threading.Barrier(8, timeout=5)
    caller = threading.get_ident()
    threads = set()
    def recognize(img, config, output_type):
        threads.add(threading.get_ident())
        barrier.wait()
        return {'value': int(img[0, 0])}
    def parse(img, scale, origin, config, data, **kwargs):
        assert threading.get_ident() == caller
        return (data['value'], scale, origin, config.split()[1])
    monkeypatch.setattr(pt.pytesseract, 'image_to_data', recognize)
    monkeypatch.setattr(pt, '_ocr_word_rows', parse)
    renders = [((np.full((1, 1), i), np.full((1, 1), i+1)), scale, (i, i))
               for i, scale in [(0, 8), (2, 6)]]
    got = list(pt._ocr_render_variants(renders, 'x', None))
    assert len(threads) == 8
    assert got == [(i+j, scale, (i, i), str(psm))
                   for i, scale in [(0, 8), (2, 6)] for j in (0, 1) for psm in (6, 11)]
