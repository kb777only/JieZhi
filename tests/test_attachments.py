from pathlib import Path
import pytest
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
from jiezhi.attachments import extract, prepare, excerpt


def test_text_encoding_and_binary_rejection(tmp_path):
    path = tmp_path / 'example.py'; path.write_text('print("借智")')
    assert '借智' in extract(path)['text']
    path.write_bytes('UTF sixteen'.encode('utf-16'))
    assert extract(path)['text'] == 'UTF sixteen'
    path.write_bytes(b'abc\x00def')
    with pytest.raises(ValueError, match='binary'): extract(path)
    path = tmp_path / 'model.gguf'; path.write_bytes(b'GGUF')
    with pytest.raises(ValueError, match='Import GGUF'): extract(path)


def test_extract_pdf_and_scanned_pdf(tmp_path):
    writer = PdfWriter(); page = writer.add_blank_page(width=400, height=400)
    font = DictionaryObject({NameObject('/Type'): NameObject('/Font'), NameObject('/Subtype'): NameObject('/Type1'), NameObject('/BaseFont'): NameObject('/Helvetica')})
    page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): writer._add_object(font)})})
    content = DecodedStreamObject(); content.set_data(b'BT /F1 12 Tf 20 200 Td (Launch code is WILLOW-742.) Tj ET')
    page[NameObject('/Contents')] = writer._add_object(content)
    path = tmp_path / 'notes.pdf'; writer.write(path)
    result = extract(path)
    assert 'WILLOW-742' in result['text'] and '[Page 1]' in result['text']
    writer = PdfWriter(); writer.add_blank_page(width=400, height=400); writer.write(path)
    with pytest.raises(ValueError, match='OCR'): extract(path)
    writer.encrypt('test password'); writer.write(path)
    with pytest.raises(ValueError, match='password'): extract(path)


def test_retrieval_and_context_are_bounded(tmp_path):
    path = tmp_path / 'launch.md'
    path.write_text('Unrelated gardening notes.\n' * 2500 + '\nLaunch code is WILLOW-742.\n' + 'More unrelated notes.\n' * 2500)
    attachment = extract(path)
    messages = [{'role': 'user', 'content': 'What is the launch code?', 'attachments': [attachment]}]
    payload, note = prepare(messages)
    assert 'WILLOW-742' in payload[-1]['content']
    assert 'bounded excerpts' in note
    assert sum(len(m['content'].encode()) for m in payload) <= 2048 - 512 - 256
    assert set(payload[-1]) == {'role', 'content'}
    messages += [{'role': 'assistant', 'content': 'It is WILLOW-742.'}, {'role': 'user', 'content': 'Repeat the launch code.'}]
    assert 'WILLOW-742' in prepare(messages)[0][-1]['content']


def test_large_unicode_and_long_prompt(tmp_path):
    path = tmp_path / 'notes.txt'; path.write_text('借智' * 110000)
    attachment = extract(path)
    assert attachment['truncated']
    payload, _ = prepare([{'role': 'user', 'content': 'Summarize', 'attachments': [attachment]}])
    assert len(payload[-1]['content'].encode()) <= 1280
    with pytest.raises(ValueError, match='too long'): prepare([{'role': 'user', 'content': 'long' * 1000}])
    with pytest.raises(ValueError, match='larger context'): prepare([{'role': 'user', 'content': 'Hi'}], context=512)
