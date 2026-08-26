export const PROCESSING_ACTIVITY = {
  ingestion: {
    label: 'Repository ingestion',
    entries: [
      'Resolving GitHub repository metadata',
      'Resolving requested ref',
      'Pinning immutable commit SHA',
      'Downloading repository archive',
      'Validating archive contents',
      'Discovering supported source files',
      'Persisting repository snapshot metadata',
    ],
  },
  analysis: {
    label: 'Structural analysis',
    entries: [
      'Loading immutable repository snapshot',
      'Discovering Python source files',
      'Parsing Python syntax trees',
      'Extracting files, classes, functions, and methods',
      'Extracting imports and inheritance',
      'Resolving conservative call references',
      'Building deterministic symbol records',
      'Finalizing structural analysis',
    ],
  },
  graph: {
    label: 'Code graph indexing',
    entries: [
      'Preparing structural records',
      'Creating repository and snapshot nodes',
      'Persisting file nodes',
      'Persisting class, function, and method nodes',
      'Persisting DECLARES and CONTAINS relationships',
      'Persisting IMPORTS relationships',
      'Persisting INHERITS relationships',
      'Persisting resolved CALLS relationships',
      'Verifying graph persistence',
    ],
  },
  vector: {
    label: 'Semantic index',
    entries: [
      'Loading analyzed symbols',
      'Building semantic source chunks',
      'Preserving source and line metadata',
      'Generating embeddings',
      'Normalizing vectors',
      'Building FAISS index',
      'Persisting vector metadata and manifest',
      'Verifying vector index integrity',
    ],
  },
  query: {
    label: 'Repository Q&A',
    entries: [
      'Validating repository snapshot',
      'Searching semantic code evidence',
      'Retrieving structural graph context',
      'Expanding bounded symbol relationships',
      'Ranking and deduplicating evidence',
      'Applying context budget',
      'Preparing grounded reasoning context',
      'Running Gemini grounded reasoning',
      'Validating structured output with Pydantic',
      'Validating supplied evidence citations',
      'Constructing grounded answer',
    ],
  },
}

export const PIPELINE_ACTIVITY_STAGES = ['ingestion', 'analysis', 'graph', 'vector']
