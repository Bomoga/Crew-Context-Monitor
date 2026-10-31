// Contract validation with ajv, loaded only in dev builds (see client.ts) so production bundles
// carry neither ajv nor the schemas.
import Ajv2020 from "ajv/dist/2020";
import type { ValidateFunction } from "ajv/dist/2020";
import status from "../../../contracts/api/status.schema.json";
import history from "../../../contracts/api/history.schema.json";
import events from "../../../contracts/api/events.schema.json";
import earthQueue from "../../../contracts/api/earth_queue.schema.json";
import earthQueueItem from "../../../contracts/api/earth_queue_item.schema.json";
import settings from "../../../contracts/api/settings.schema.json";
import checkinResponse from "../../../contracts/api/checkin_response.schema.json";

export type ContractKind =
  | "status"
  | "history"
  | "events"
  | "earth_queue"
  | "earth_queue_item"
  | "settings"
  | "checkin_response";

const SCHEMAS: Record<ContractKind, object> = {
  status,
  history,
  events,
  earth_queue: earthQueue,
  earth_queue_item: earthQueueItem,
  settings,
  checkin_response: checkinResponse,
};

const ajv = new Ajv2020({ allErrors: true, strict: false });
const validators = new Map<ContractKind, ValidateFunction>();

function validatorFor(kind: ContractKind): ValidateFunction {
  let validate = validators.get(kind);
  if (!validate) {
    validate = ajv.compile(SCHEMAS[kind]);
    validators.set(kind, validate);
  }
  return validate;
}

/** Human-readable contract violations for `data` against the schema for `kind` (empty if valid). */
export function contractViolations(kind: ContractKind, data: unknown): string[] {
  const validate = validatorFor(kind);
  if (validate(data)) return [];
  return (validate.errors ?? []).map(
    (e) => `${e.instancePath || "<root>"}: ${e.message ?? "invalid"}`,
  );
}
