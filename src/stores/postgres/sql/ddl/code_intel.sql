-- code_intel schema: corpus chunks + embeddings for the code intelligence agent.
-- Embedding dim 768 matches jinaai/jina-embeddings-v2-base-code.

create extension if not exists vector;

create schema if not exists code_intel;

create table code_intel.chunks
(
    chunk_id       bigserial primary key,
    splitter_name  varchar(60)              not null,
    project_folder varchar(255)             not null,
    file_name      varchar(255)             not null,
    file_type      varchar(20)              not null,
    kind           varchar(20)              not null,
    start_line     integer                  not null,
    end_line       integer                  not null,
    text           text                     not null,
    last_modified  timestamp with time zone not null,
    vector         vector(768)              not null,
    -- Structural metadata: populated by tree-sitter / heading splitters,
    -- NULL for naive (FixedSplitter) chunks. All four travel together or all are NULL.
    symbol_name    varchar(200),
    symbol_kind    varchar(20),
    parent_symbol  varchar(200),
    heading_path   text[],
    created_at     timestamp with time zone default now() not null,
    constraint code_intel_chunks_kind_ck
        check (kind in ('source', 'test', 'doc', 'config', 'template')),
    constraint code_intel_chunks_file_type_ck
        check (file_type in ('python', 'markdown', 'json', 'yaml', 'toml', 'template', 'text')),
    constraint code_intel_chunks_symbol_kind_ck
        check (symbol_kind is null or symbol_kind in
               ('function', 'class', 'method', 'module', 'imports', 'heading_section')),
    constraint code_intel_chunks_symbol_grouping_ck
        check ((symbol_name is null) = (symbol_kind is null)),
    constraint code_intel_chunks_line_ck
        check (start_line >= 1 and end_line >= start_line)
);

-- HNSW cosine index for semantic_search()
create index idx_code_intel_chunks_vector
    on code_intel.chunks using hnsw (vector vector_cosine_ops);

-- Filter indexes for metadata-scoped retrieval (kind, file_type, path)
create index idx_code_intel_chunks_filters
    on code_intel.chunks (kind, file_type);

create index idx_code_intel_chunks_path
    on code_intel.chunks (project_folder, file_name);

-- Symbol lookups: keyword_search for identifier-heavy queries
-- ("find usages of _balance_dangling_tool_calls") hits this directly.
create index idx_code_intel_chunks_symbol on code_intel.chunks (symbol_name)
    where symbol_name is not null;
create index idx_code_intel_chunks_symbol_kind on code_intel.chunks (symbol_kind)
    where symbol_kind is not null;
