import type { components } from "./api.generated";

// Generated from the integrated FastAPI app; runtime decoders still validate responses.
type Schemas = components["schemas"];
export type GraphNode = Schemas["GraphNode"];
export type KnowledgeGraph = Schemas["GraphResponse"];
export type DecisionTrace = Schemas["DecisionTrace"];
export type PublicItem = Schemas["LearnerItem"];
export type TopicRequest = Schemas["TopicInput"];
export type Tier = TopicRequest["tier"];
export type ResearchMode = TopicRequest["mode"];
export type Citation = Schemas["Citation"];
export type UploadResult = Schemas["UploadResponse"];
export type Placement = Schemas["PlacementResponse"];
export type AttemptResult = Schemas["AttemptResponse"];
export type HintResult = Schemas["HintResponse"];
export type ReviewCard = Schemas["ReviewCard"];

export type Source = Schemas["TopicSource"];
export type TopicSnapshot = Schemas["TopicState"];
