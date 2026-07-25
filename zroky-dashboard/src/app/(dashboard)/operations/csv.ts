type OperationsCsvRow = {
  agent: string;
  age: string;
  item: string;
  owner: string;
  runId: string;
  severity: string;
  source: string;
  state: string;
  type: string;
};

function csvCell(value: string): string {
  return `"${value.replace(/"/g, '""')}"`;
}

export function operationsRowsCsv(rows: OperationsCsvRow[]): string {
  const header = ["severity", "type", "item", "source", "agent_workflow", "state", "age", "owner", "run_id"];
  const body = rows.map((row) =>
    [row.severity, row.type, row.item, row.source, row.agent, row.state, row.age, row.owner, row.runId].map(csvCell).join(","),
  );
  return [header.join(","), ...body].join("\n");
}
