from cortex_vec import store, parser


def test_bm25_doc_from_fields():
    text = "---\ntitle: Nginx 憑證\nrepos: [libsynow3, nginx]\n---\n# H\n憑證 certbot renew\n"
    fm, body = parser.parse_document(text)
    doc = store.bm25_doc_from_fields("Notes/Nginx/cert.md", fm, body)
    assert doc["id"] == "Notes/Nginx/cert.md"
    assert doc["title"] == "Nginx 憑證"
    assert doc["type"] == "note"
    assert doc["category"] == "Nginx"
    assert "libsynow3" in doc["repos"] and "nginx" in doc["repos"]
    assert doc["summary"]  # extracted first content line
