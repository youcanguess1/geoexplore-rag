# Geological Data Policy

This release contains the geological document manifest but intentionally excludes the original PDF binaries. Each document's filename, source description, parser, metadata, and SHA-256 are listed in `manifests/geological_documents.json`.

Before using a PDF, obtain it from the stated source, verify that local use and redistribution are permitted, and verify its SHA-256 against the manifest. Place permitted files in `data/local/geological_knowledge`; that directory is local-only and is ignored by version control.

The evaluated BM25 baseline used six documents and 1006 chunks with corpus fingerprint `07931977ad3ff8a5ae743b5ed96ea92d0c87f0b4a8fb6a1aaa1be7e72ef2575f`. Substituting PDFs, parser versions, or chunking settings changes the corpus identity and invalidates direct comparison with the recorded evaluation evidence.
