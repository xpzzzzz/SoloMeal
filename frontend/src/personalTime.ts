export type TimeEstimate = {
	recipe_id: string;
	recipe_version: number;
	servings: number;
	standard_minutes: number;
	sample_count: number;
	sample_median: number | null;
	weight: number;
	estimated_minutes: number;
	source: 'standard' | 'personalized' | 'standard_disabled';
};

// One wording for one number, so the card never claims more than the server returned:
// the standard time stays visible, and a personal estimate is only named when samples built it.
// A disabled switch is the reason standard time applies even with no history, so it keeps saying
// so; only the record count it left unused is mentioned when there actually are records.
export function timeLabel(estimate: TimeEstimate): string {
	const standard = `标准${estimate.standard_minutes}分钟`;
	if (estimate.source === 'personalized')
		return `${standard} / 你的预计${estimate.estimated_minutes}分钟，基于${estimate.sample_count}次记录`;
	if (estimate.source === 'standard_disabled')
		return estimate.sample_count
			? `${standard}，已关闭个人用时估计（另有${estimate.sample_count}次记录未使用）`
			: `${standard}，已关闭个人用时估计`;
	return `${standard}，暂无个人记录`;
}
