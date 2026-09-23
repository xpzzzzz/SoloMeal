import test from 'node:test';
import assert from 'node:assert/strict';
import {timeLabel} from '../.test-build/personalTime.js';

const base = {
	recipe_id: 'r1', recipe_version: 1, servings: 2, standard_minutes: 20,
	sample_count: 0, sample_median: null, weight: 0, estimated_minutes: 20, source: 'standard',
};

test('a recipe without my history shows only the standard time', () => {
	assert.equal(timeLabel(base), '标准20分钟，暂无个人记录');
});

test('a personal estimate is named together with the standard time and its sample count', () => {
	assert.equal(timeLabel({...base, sample_count: 3, sample_median: 30, weight: 0.5,
		estimated_minutes: 25, source: 'personalized'}),
	'标准20分钟 / 你的预计25分钟，基于3次记录');
	assert.equal(timeLabel({...base, sample_count: 1, sample_median: 40, weight: 0.25,
		estimated_minutes: 25, source: 'personalized'}),
	'标准20分钟 / 你的预计25分钟，基于1次记录');
});

test('an estimate equal to the standard time is still reported as an estimate', () => {
	assert.equal(timeLabel({...base, sample_count: 2, sample_median: 20, weight: 0.4,
		estimated_minutes: 20, source: 'personalized'}),
	'标准20分钟 / 你的预计20分钟，基于2次记录');
});

test('the switch off reports standard filtering and names the records it left unused', () => {
	assert.equal(timeLabel({...base, sample_count: 4, sample_median: 45, weight: 0,
		estimated_minutes: 20, source: 'standard_disabled'}),
	'标准20分钟，已关闭个人用时估计（另有4次记录未使用）');
});

test('the switch off with no history yet says so without claiming unused records', () => {
	assert.equal(timeLabel({...base, source: 'standard_disabled'}),
	'标准20分钟，已关闭个人用时估计');
});

test('only the standard minutes appear when nothing personal backs the card', () => {
	assert.doesNotMatch(timeLabel(base), /你的预计/);
	assert.equal(timeLabel(base).includes('25'), false);
});
