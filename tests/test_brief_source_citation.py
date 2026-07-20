from app.services.rag.chunk_and_ingest import brief_source_citation, format_source_citation


def test_brief_source_citation_author_and_year():
    full = format_source_citation(
        {
            "title": "Some review",
            "author": "Maselli F",
            "year": "2022",
            "authority": "Disability and Rehabilitation",
            "doi": "https://doi.org/10.1080/example",
        }
    )
    assert brief_source_citation(full) == "Maselli F (2022)"


def test_brief_source_citation_fallback_when_unparsed():
    assert brief_source_citation("unknown-id") == "unknown-id"
