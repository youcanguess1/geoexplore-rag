import type { ChangeEvent } from "react";
import type { RetrievalFilters } from "../types";

const DOCUMENT_TYPES: { value: RetrievalFilters["document_types"][number]; label: string }[] = [
  { value: "report", label: "报告" },
  { value: "technical_report", label: "技术报告" },
  { value: "textbook", label: "教材" },
  { value: "paper", label: "论文" },
  { value: "standard", label: "标准" },
  { value: "review", label: "综述" },
];

const DOCUMENT_IDS = [
  "geo-1996-21", "geo-fs11503", "geo-of12-1191", "geo-report-1989-4195",
  "geo-s10950-021-10042-z", "geo-twri-2-d2",
];

interface RetrievalFiltersProps {
  value: RetrievalFilters;
  disabled: boolean;
  onChange: (filters: RetrievalFilters) => void;
}

function toggle<T extends string>(values: T[], value: T): T[] {
  return values.includes(value) ? values.filter((item) => item !== value) : [...values, value];
}

export function RetrievalFiltersPanel({ value, disabled, onChange }: RetrievalFiltersProps) {
  function documentIdsChange(event: ChangeEvent<HTMLInputElement>) {
    onChange({
      ...value,
      document_ids: event.target.value.split(",").map((item) => item.trim()).filter(Boolean),
    });
  }

  return <section className="filter-panel" aria-label="检索范围">
    <div className="filter-heading"><strong>资料范围</strong><span>同类条件任选其一，不同条件同时满足</span></div>
    <fieldset disabled={disabled}>
      <legend>文档类型</legend>
      <div className="filter-options">
        {DOCUMENT_TYPES.map((item) => <label key={item.value}>
          <input type="checkbox" checked={value.document_types.includes(item.value)} onChange={() => onChange({ ...value, document_types: toggle(value.document_types, item.value) })} />
          <span>{item.label}</span>
        </label>)}
      </div>
    </fieldset>
    <fieldset disabled={disabled}>
      <legend>语言</legend>
      <div className="filter-options">
        <label><input type="checkbox" checked={value.languages.includes("en")} onChange={() => onChange({ ...value, languages: toggle(value.languages, "en") })} /><span>英语</span></label>
      </div>
    </fieldset>
    <label className="document-id-input">文档 ID（逗号分隔）
      <input value={value.document_ids.join(", ")} disabled={disabled} list="registered-document-ids" onChange={documentIdsChange} placeholder="例如 geo-twri-2-d2" />
      <datalist id="registered-document-ids">{DOCUMENT_IDS.map((id) => <option key={id} value={id} />)}</datalist>
    </label>
  </section>;
}
