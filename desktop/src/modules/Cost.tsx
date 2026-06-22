import { useTelemetry } from "../telemetry";

type CostSnapshot = {
  in_tokens: number;
  out_tokens: number;
  last_in: number;
  last_out: number;
  cache_read: number;
  cache_write: number;
  cost_usd: number;
};

const fmt = (n: number) => n.toLocaleString();

/** Token Usage tile — running session cost + last-call delta, pushed after every turn (telemetry
 * topic "cost"). Read-only view; the daemon already computes cost_usd (M12). */
export function CostModule() {
  const c = useTelemetry<CostSnapshot>("cost");
  if (!c) return <p className="module-empty">no turns yet</p>;
  return (
    <div className="cost">
      <div className="cost-headline">
        <span className="cost-amount">${c.cost_usd.toFixed(4)}</span>
        <span className="cost-caption">session cost</span>
      </div>
      <dl className="cost-stats">
        <div>
          <dt>in</dt>
          <dd>{fmt(c.in_tokens)}</dd>
        </div>
        <div>
          <dt>cached</dt>
          <dd>{fmt(c.cache_read)}</dd>
        </div>
        <div>
          <dt>out</dt>
          <dd>{fmt(c.out_tokens)}</dd>
        </div>
        <div>
          <dt>last</dt>
          <dd>
            {fmt(c.last_in)} / {fmt(c.last_out)}
          </dd>
        </div>
      </dl>
    </div>
  );
}
