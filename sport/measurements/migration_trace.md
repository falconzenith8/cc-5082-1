# 时钟迁移不一致追踪

时间单位：秒；承诺约定：commit_at=承诺瞬间赛钟剩余秒。

## 最终状态字段差异（忽略墙钟/赛钟实时值与修订号）
- 场景 dense_interrupts 字段 `event_count`：{'fixed_step@1s': 23, 'fixed_step@0.25s': 27, 'event_jump': 42}

## 裁决分歧（同一意图在不同驱动上的接受/拒绝）
| 场景 | 意图 | 各驱动裁决 |
|---|---|---|
| buzzer_beater | goal_a_last_second | `{"fixed_step@1s": "reject:shot_requires_live", "fixed_step@0.25s": "accept", "event_jump": "accept"}` |
| buzzer_beater | late_after_buzzer | `{"fixed_step@1s": "reject:stale_turn_id", "fixed_step@0.25s": "reject:team_without_possession", "event_jump": "reject:team_without_possession"}` |
| buzzer_beater | late_buzzer_beater | `{"fixed_step@1s": "accept", "fixed_step@0.25s": "reject:team_without_possession", "event_jump": "reject:team_without_possession"}` |
| dense_interrupts | resume_1 | `{"fixed_step@1s": "reject:resume_wrong_phase", "fixed_step@0.25s": "accept", "event_jump": "accept"}` |
| dense_interrupts | resume_10 | `{"fixed_step@1s": "reject:resume_wrong_phase", "fixed_step@0.25s": "reject:resume_wrong_phase", "event_jump": "accept"}` |
| dense_interrupts | resume_11 | `{"fixed_step@1s": "reject:resume_wrong_phase", "fixed_step@0.25s": "reject:resume_wrong_phase", "event_jump": "accept"}` |
| dense_interrupts | resume_12 | `{"fixed_step@1s": "reject:resume_wrong_phase", "fixed_step@0.25s": "reject:resume_wrong_phase", "event_jump": "accept"}` |
| dense_interrupts | resume_13 | `{"fixed_step@1s": "reject:resume_wrong_phase", "fixed_step@0.25s": "reject:resume_wrong_phase", "event_jump": "accept"}` |
| dense_interrupts | resume_14 | `{"fixed_step@1s": "reject:resume_wrong_phase", "fixed_step@0.25s": "reject:resume_wrong_phase", "event_jump": "accept"}` |
| dense_interrupts | resume_15 | `{"fixed_step@1s": "reject:resume_wrong_phase", "fixed_step@0.25s": "reject:resume_wrong_phase", "event_jump": "accept"}` |
| dense_interrupts | resume_16 | `{"fixed_step@1s": "reject:resume_wrong_phase", "fixed_step@0.25s": "reject:resume_wrong_phase", "event_jump": "accept"}` |
| dense_interrupts | resume_17 | `{"fixed_step@1s": "reject:resume_wrong_phase", "fixed_step@0.25s": "reject:resume_wrong_phase", "event_jump": "accept"}` |
| dense_interrupts | resume_18 | `{"fixed_step@1s": "reject:resume_wrong_phase", "fixed_step@0.25s": "reject:resume_wrong_phase", "event_jump": "accept"}` |
| dense_interrupts | resume_19 | `{"fixed_step@1s": "reject:resume_wrong_phase", "fixed_step@0.25s": "reject:resume_wrong_phase", "event_jump": "accept"}` |
| dense_interrupts | resume_2 | `{"fixed_step@1s": "reject:resume_wrong_phase", "fixed_step@0.25s": "accept", "event_jump": "accept"}` |
| dense_interrupts | resume_3 | `{"fixed_step@1s": "reject:resume_wrong_phase", "fixed_step@0.25s": "accept", "event_jump": "accept"}` |
| dense_interrupts | resume_4 | `{"fixed_step@1s": "reject:resume_wrong_phase", "fixed_step@0.25s": "accept", "event_jump": "accept"}` |
| dense_interrupts | resume_5 | `{"fixed_step@1s": "reject:resume_wrong_phase", "fixed_step@0.25s": "reject:resume_wrong_phase", "event_jump": "accept"}` |
| dense_interrupts | resume_6 | `{"fixed_step@1s": "reject:resume_wrong_phase", "fixed_step@0.25s": "reject:resume_wrong_phase", "event_jump": "accept"}` |
| dense_interrupts | resume_7 | `{"fixed_step@1s": "reject:resume_wrong_phase", "fixed_step@0.25s": "reject:resume_wrong_phase", "event_jump": "accept"}` |
| dense_interrupts | resume_8 | `{"fixed_step@1s": "reject:resume_wrong_phase", "fixed_step@0.25s": "reject:resume_wrong_phase", "event_jump": "accept"}` |
| dense_interrupts | resume_9 | `{"fixed_step@1s": "reject:resume_wrong_phase", "fixed_step@0.25s": "reject:resume_wrong_phase", "event_jump": "accept"}` |

## 时钟台账业务锚点差异（按迁移 note 对齐，全量 tick 见 raw_runs.json）
共 104 条锚点差异，根因均为固定步把迁移量化到步网格。
| 场景 | 驱动 | 锚点序号 | 驱动条目 | event_jump 条目 |
|---|---|---:|---|---|
| buzzer_beater | fixed_step@1s | 2 | `{"wall_at": 20.0, "phase": "LIVE", "game_remaining_before": 1.0, "game_remaining_after": 0.0, "note": "buzzer_zero"}` | `{"wall_at": 20.0, "phase": "LIVE", "game_remaining_before": 0.5, "game_remaining_after": 0.0, "note": "buzzer_zero"}` |
| buzzer_beater | fixed_step@0.25s | 2 | `{"wall_at": 20.0, "phase": "LIVE", "game_remaining_before": 0.25, "game_remaining_after": 0.0, "note": "buzzer_zero"}` | `{"wall_at": 20.0, "phase": "LIVE", "game_remaining_before": 0.5, "game_remaining_after": 0.0, "note": "buzzer_zero"}` |
| coincident_deadlines | fixed_step@1s | 4 | `{"wall_at": 21.0, "phase": "LIVE", "game_remaining_before": 1.0, "game_remaining_after": 0.0, "note": "buzzer_zero"}` | `{"wall_at": 22.0, "phase": "LIVE", "game_remaining_before": 15.0, "game_remaining_after": 0.0, "note": "buzzer_zero"}` |
| coincident_deadlines | fixed_step@1s | 5 | `{"wall_at": 21.0, "phase": "STOPPED", "game_remaining_before": 0.0, "game_remaining_after": 0.0, "note": "buzzer_zero_freeze"}` | `{"wall_at": 22.0, "phase": "STOPPED", "game_remaining_before": 0.0, "game_remaining_after": 0.0, "note": "buzzer_zero_freeze"}` |
| coincident_deadlines | fixed_step@0.25s | 4 | `{"wall_at": 21.0, "phase": "LIVE", "game_remaining_before": 0.25, "game_remaining_after": 0.0, "note": "buzzer_zero"}` | `{"wall_at": 22.0, "phase": "LIVE", "game_remaining_before": 15.0, "game_remaining_after": 0.0, "note": "buzzer_zero"}` |
| coincident_deadlines | fixed_step@0.25s | 5 | `{"wall_at": 21.0, "phase": "STOPPED", "game_remaining_before": 0.0, "game_remaining_after": 0.0, "note": "buzzer_zero_freeze"}` | `{"wall_at": 22.0, "phase": "STOPPED", "game_remaining_before": 0.0, "game_remaining_after": 0.0, "note": "buzzer_zero_freeze"}` |
| zero_duration_turn | fixed_step@1s | 2 | `{"wall_at": 20.0, "phase": "LIVE", "game_remaining_before": 1.0, "game_remaining_after": 0.0, "note": "buzzer_zero"}` | `{"wall_at": 22.0, "phase": "LIVE", "game_remaining_before": 18.0, "game_remaining_after": 0.0, "note": "buzzer_zero"}` |
| zero_duration_turn | fixed_step@1s | 3 | `{"wall_at": 20.0, "phase": "STOPPED", "game_remaining_before": 0.0, "game_remaining_after": 0.0, "note": "buzzer_zero_freeze"}` | `{"wall_at": 22.0, "phase": "STOPPED", "game_remaining_before": 0.0, "game_remaining_after": 0.0, "note": "buzzer_zero_freeze"}` |
| zero_duration_turn | fixed_step@0.25s | 2 | `{"wall_at": 20.0, "phase": "LIVE", "game_remaining_before": 0.25, "game_remaining_after": 0.0, "note": "buzzer_zero"}` | `{"wall_at": 22.0, "phase": "LIVE", "game_remaining_before": 18.0, "game_remaining_after": 0.0, "note": "buzzer_zero"}` |
| zero_duration_turn | fixed_step@0.25s | 3 | `{"wall_at": 20.0, "phase": "STOPPED", "game_remaining_before": 0.0, "game_remaining_after": 0.0, "note": "buzzer_zero_freeze"}` | `{"wall_at": 22.0, "phase": "STOPPED", "game_remaining_before": 0.0, "game_remaining_after": 0.0, "note": "buzzer_zero_freeze"}` |
| resume_instant | fixed_step@1s | 2 | `{"wall_at": 1.0, "phase": "STOPPED", "game_remaining_before": 19.0, "game_remaining_after": 19.0, "note": "sub_step"}` | `{"wall_at": 0.6, "phase": "STOPPED", "game_remaining_before": 19.4, "game_remaining_after": 19.4, "note": "sub_step"}` |
| resume_instant | fixed_step@1s | 3 | `{"wall_at": 1.0, "phase": "LIVE", "game_remaining_before": 19.0, "game_remaining_after": 19.0, "note": "resume"}` | `{"wall_at": 0.9, "phase": "LIVE", "game_remaining_before": 19.4, "game_remaining_after": 19.4, "note": "resume"}` |
| resume_instant | fixed_step@1s | 4 | `{"wall_at": 20.0, "phase": "LIVE", "game_remaining_before": 1.0, "game_remaining_after": 0.0, "note": "buzzer_zero"}` | `{"wall_at": 22.0, "phase": "LIVE", "game_remaining_before": 15.3, "game_remaining_after": 0.0, "note": "buzzer_zero"}` |
| resume_instant | fixed_step@1s | 5 | `{"wall_at": 20.0, "phase": "STOPPED", "game_remaining_before": 0.0, "game_remaining_after": 0.0, "note": "buzzer_zero_freeze"}` | `{"wall_at": 22.0, "phase": "STOPPED", "game_remaining_before": 0.0, "game_remaining_after": 0.0, "note": "buzzer_zero_freeze"}` |
| resume_instant | fixed_step@0.25s | 2 | `{"wall_at": 0.75, "phase": "STOPPED", "game_remaining_before": 19.25, "game_remaining_after": 19.25, "note": "sub_step"}` | `{"wall_at": 0.6, "phase": "STOPPED", "game_remaining_before": 19.4, "game_remaining_after": 19.4, "note": "sub_step"}` |
| resume_instant | fixed_step@0.25s | 3 | `{"wall_at": 1.0, "phase": "LIVE", "game_remaining_before": 19.25, "game_remaining_after": 19.25, "note": "resume"}` | `{"wall_at": 0.9, "phase": "LIVE", "game_remaining_before": 19.4, "game_remaining_after": 19.4, "note": "resume"}` |
| resume_instant | fixed_step@0.25s | 4 | `{"wall_at": 20.25, "phase": "LIVE", "game_remaining_before": 0.25, "game_remaining_after": 0.0, "note": "buzzer_zero"}` | `{"wall_at": 22.0, "phase": "LIVE", "game_remaining_before": 15.3, "game_remaining_after": 0.0, "note": "buzzer_zero"}` |
| resume_instant | fixed_step@0.25s | 5 | `{"wall_at": 20.25, "phase": "STOPPED", "game_remaining_before": 0.0, "game_remaining_after": 0.0, "note": "buzzer_zero_freeze"}` | `{"wall_at": 22.0, "phase": "STOPPED", "game_remaining_before": 0.0, "game_remaining_after": 0.0, "note": "buzzer_zero_freeze"}` |
| full_regulation_ot | fixed_step@1s | 14 | `{"wall_at": 80.0, "phase": "LIVE", "game_remaining_before": 1.0, "game_remaining_after": 0.0, "note": "buzzer_zero"}` | `{"wall_at": 80.0, "phase": "LIVE", "game_remaining_before": 0.5, "game_remaining_after": 0.0, "note": "buzzer_zero"}` |
| full_regulation_ot | fixed_step@1s | 18 | `{"wall_at": 90.0, "phase": "LIVE", "game_remaining_before": 1.0, "game_remaining_after": 0.0, "note": "buzzer_zero"}` | `{"wall_at": 91.0, "phase": "LIVE", "game_remaining_before": 0.5, "game_remaining_after": 0.0, "note": "buzzer_zero"}` |
| full_regulation_ot | fixed_step@1s | 19 | `{"wall_at": 90.0, "phase": "STOPPED", "game_remaining_before": 0.0, "game_remaining_after": 0.0, "note": "buzzer_zero_freeze"}` | `{"wall_at": 91.0, "phase": "STOPPED", "game_remaining_before": 0.0, "game_remaining_after": 0.0, "note": "buzzer_zero_freeze"}` |
| full_regulation_ot | fixed_step@0.25s | 2 | `{"wall_at": 20.0, "phase": "LIVE", "game_remaining_before": 0.25, "game_remaining_after": 0.0, "note": "buzzer_zero"}` | `{"wall_at": 20.0, "phase": "LIVE", "game_remaining_before": 1.0, "game_remaining_after": 0.0, "note": "buzzer_zero"}` |
| full_regulation_ot | fixed_step@0.25s | 6 | `{"wall_at": 40.0, "phase": "LIVE", "game_remaining_before": 0.25, "game_remaining_after": 0.0, "note": "buzzer_zero"}` | `{"wall_at": 40.0, "phase": "LIVE", "game_remaining_before": 1.0, "game_remaining_after": 0.0, "note": "buzzer_zero"}` |
| full_regulation_ot | fixed_step@0.25s | 10 | `{"wall_at": 60.0, "phase": "LIVE", "game_remaining_before": 0.25, "game_remaining_after": 0.0, "note": "buzzer_zero"}` | `{"wall_at": 60.0, "phase": "LIVE", "game_remaining_before": 1.0, "game_remaining_after": 0.0, "note": "buzzer_zero"}` |
| full_regulation_ot | fixed_step@0.25s | 14 | `{"wall_at": 80.0, "phase": "LIVE", "game_remaining_before": 0.25, "game_remaining_after": 0.0, "note": "buzzer_zero"}` | `{"wall_at": 80.0, "phase": "LIVE", "game_remaining_before": 0.5, "game_remaining_after": 0.0, "note": "buzzer_zero"}` |
| full_regulation_ot | fixed_step@0.25s | 18 | `{"wall_at": 90.0, "phase": "LIVE", "game_remaining_before": 0.25, "game_remaining_after": 0.0, "note": "buzzer_zero"}` | `{"wall_at": 91.0, "phase": "LIVE", "game_remaining_before": 0.5, "game_remaining_after": 0.0, "note": "buzzer_zero"}` |
| full_regulation_ot | fixed_step@0.25s | 19 | `{"wall_at": 90.0, "phase": "STOPPED", "game_remaining_before": 0.0, "game_remaining_after": 0.0, "note": "buzzer_zero_freeze"}` | `{"wall_at": 91.0, "phase": "STOPPED", "game_remaining_before": 0.0, "game_remaining_after": 0.0, "note": "buzzer_zero_freeze"}` |
| dense_interrupts | fixed_step@1s | 3 | `{"wall_at": 2.0, "phase": "LIVE", "game_remaining_before": 19.0, "game_remaining_after": 19.0, "note": "resume"}` | `{"wall_at": 1.2, "phase": "LIVE", "game_remaining_before": 19.0, "game_remaining_after": 19.0, "note": "resume"}` |
| dense_interrupts | fixed_step@1s | 4 | `{"wall_at": 2.0, "phase": "STOPPED", "game_remaining_before": 19.0, "game_remaining_after": 19.0, "note": "dense_pause_1"}` | `{"wall_at": 1.4, "phase": "STOPPED", "game_remaining_before": 18.8, "game_remaining_after": 18.8, "note": "dense_pause_1"}` |
| dense_interrupts | fixed_step@1s | 5 | `null` | `{"wall_at": 1.6, "phase": "LIVE", "game_remaining_before": 18.8, "game_remaining_after": 18.8, "note": "resume"}` |
| dense_interrupts | fixed_step@1s | 6 | `null` | `{"wall_at": 1.8, "phase": "STOPPED", "game_remaining_before": 18.6, "game_remaining_after": 18.6, "note": "dense_pause_2"}` |
| dense_interrupts | fixed_step@1s | 7 | `null` | `{"wall_at": 2.0, "phase": "LIVE", "game_remaining_before": 18.6, "game_remaining_after": 18.6, "note": "resume"}` |
| dense_interrupts | fixed_step@1s | 8 | `null` | `{"wall_at": 2.2, "phase": "STOPPED", "game_remaining_before": 18.4, "game_remaining_after": 18.4, "note": "dense_pause_3"}` |
| dense_interrupts | fixed_step@1s | 9 | `null` | `{"wall_at": 2.4, "phase": "LIVE", "game_remaining_before": 18.4, "game_remaining_after": 18.4, "note": "resume"}` |
| dense_interrupts | fixed_step@1s | 10 | `null` | `{"wall_at": 2.6, "phase": "STOPPED", "game_remaining_before": 18.2, "game_remaining_after": 18.2, "note": "dense_pause_4"}` |
| dense_interrupts | fixed_step@1s | 11 | `null` | `{"wall_at": 2.8, "phase": "LIVE", "game_remaining_before": 18.2, "game_remaining_after": 18.2, "note": "resume"}` |
| dense_interrupts | fixed_step@1s | 12 | `null` | `{"wall_at": 3.0, "phase": "STOPPED", "game_remaining_before": 18.0, "game_remaining_after": 18.0, "note": "dense_pause_5"}` |
| dense_interrupts | fixed_step@1s | 13 | `null` | `{"wall_at": 3.2, "phase": "LIVE", "game_remaining_before": 18.0, "game_remaining_after": 18.0, "note": "resume"}` |
| dense_interrupts | fixed_step@1s | 14 | `null` | `{"wall_at": 3.4, "phase": "STOPPED", "game_remaining_before": 17.8, "game_remaining_after": 17.8, "note": "dense_pause_6"}` |
| dense_interrupts | fixed_step@1s | 15 | `null` | `{"wall_at": 3.6, "phase": "LIVE", "game_remaining_before": 17.8, "game_remaining_after": 17.8, "note": "resume"}` |
| dense_interrupts | fixed_step@1s | 16 | `null` | `{"wall_at": 3.8, "phase": "STOPPED", "game_remaining_before": 17.6, "game_remaining_after": 17.6, "note": "dense_pause_7"}` |
| dense_interrupts | fixed_step@1s | 17 | `null` | `{"wall_at": 4.0, "phase": "LIVE", "game_remaining_before": 17.6, "game_remaining_after": 17.6, "note": "resume"}` |
| dense_interrupts | fixed_step@1s | 18 | `null` | `{"wall_at": 4.2, "phase": "STOPPED", "game_remaining_before": 17.4, "game_remaining_after": 17.4, "note": "dense_pause_8"}` |
| dense_interrupts | fixed_step@1s | 19 | `null` | `{"wall_at": 4.4, "phase": "LIVE", "game_remaining_before": 17.4, "game_remaining_after": 17.4, "note": "resume"}` |
| dense_interrupts | fixed_step@1s | 20 | `null` | `{"wall_at": 4.6, "phase": "STOPPED", "game_remaining_before": 17.2, "game_remaining_after": 17.2, "note": "dense_pause_9"}` |
| dense_interrupts | fixed_step@1s | 21 | `null` | `{"wall_at": 4.8, "phase": "LIVE", "game_remaining_before": 17.2, "game_remaining_after": 17.2, "note": "resume"}` |
| dense_interrupts | fixed_step@1s | 22 | `null` | `{"wall_at": 5.0, "phase": "STOPPED", "game_remaining_before": 17.0, "game_remaining_after": 17.0, "note": "dense_pause_10"}` |
| dense_interrupts | fixed_step@1s | 23 | `null` | `{"wall_at": 5.2, "phase": "LIVE", "game_remaining_before": 17.0, "game_remaining_after": 17.0, "note": "resume"}` |
| dense_interrupts | fixed_step@1s | 24 | `null` | `{"wall_at": 5.4, "phase": "STOPPED", "game_remaining_before": 16.8, "game_remaining_after": 16.8, "note": "dense_pause_11"}` |
| dense_interrupts | fixed_step@1s | 25 | `null` | `{"wall_at": 5.6, "phase": "LIVE", "game_remaining_before": 16.8, "game_remaining_after": 16.8, "note": "resume"}` |
| dense_interrupts | fixed_step@1s | 26 | `null` | `{"wall_at": 5.8, "phase": "STOPPED", "game_remaining_before": 16.6, "game_remaining_after": 16.6, "note": "dense_pause_12"}` |
| dense_interrupts | fixed_step@1s | 27 | `null` | `{"wall_at": 6.0, "phase": "LIVE", "game_remaining_before": 16.6, "game_remaining_after": 16.6, "note": "resume"}` |
| dense_interrupts | fixed_step@1s | 28 | `null` | `{"wall_at": 6.2, "phase": "STOPPED", "game_remaining_before": 16.4, "game_remaining_after": 16.4, "note": "dense_pause_13"}` |
| dense_interrupts | fixed_step@1s | 29 | `null` | `{"wall_at": 6.4, "phase": "LIVE", "game_remaining_before": 16.4, "game_remaining_after": 16.4, "note": "resume"}` |
| dense_interrupts | fixed_step@1s | 30 | `null` | `{"wall_at": 6.6, "phase": "STOPPED", "game_remaining_before": 16.2, "game_remaining_after": 16.2, "note": "dense_pause_14"}` |
| dense_interrupts | fixed_step@1s | 31 | `null` | `{"wall_at": 6.8, "phase": "LIVE", "game_remaining_before": 16.2, "game_remaining_after": 16.2, "note": "resume"}` |
| dense_interrupts | fixed_step@1s | 32 | `null` | `{"wall_at": 7.0, "phase": "STOPPED", "game_remaining_before": 16.0, "game_remaining_after": 16.0, "note": "dense_pause_15"}` |
| dense_interrupts | fixed_step@1s | 33 | `null` | `{"wall_at": 7.2, "phase": "LIVE", "game_remaining_before": 16.0, "game_remaining_after": 16.0, "note": "resume"}` |
| dense_interrupts | fixed_step@1s | 34 | `null` | `{"wall_at": 7.4, "phase": "STOPPED", "game_remaining_before": 15.8, "game_remaining_after": 15.8, "note": "dense_pause_16"}` |
| dense_interrupts | fixed_step@1s | 35 | `null` | `{"wall_at": 7.6, "phase": "LIVE", "game_remaining_before": 15.8, "game_remaining_after": 15.8, "note": "resume"}` |
| dense_interrupts | fixed_step@1s | 36 | `null` | `{"wall_at": 7.8, "phase": "STOPPED", "game_remaining_before": 15.6, "game_remaining_after": 15.6, "note": "dense_pause_17"}` |
| dense_interrupts | fixed_step@1s | 37 | `null` | `{"wall_at": 8.0, "phase": "LIVE", "game_remaining_before": 15.6, "game_remaining_after": 15.6, "note": "resume"}` |
| dense_interrupts | fixed_step@1s | 38 | `null` | `{"wall_at": 8.2, "phase": "STOPPED", "game_remaining_before": 15.4, "game_remaining_after": 15.4, "note": "dense_pause_18"}` |
| dense_interrupts | fixed_step@1s | 39 | `null` | `{"wall_at": 8.4, "phase": "LIVE", "game_remaining_before": 15.4, "game_remaining_after": 15.4, "note": "resume"}` |
| dense_interrupts | fixed_step@1s | 40 | `null` | `{"wall_at": 8.6, "phase": "STOPPED", "game_remaining_before": 15.2, "game_remaining_after": 15.2, "note": "dense_pause_19"}` |
| dense_interrupts | fixed_step@1s | 41 | `null` | `{"wall_at": 8.8, "phase": "LIVE", "game_remaining_before": 15.2, "game_remaining_after": 15.2, "note": "resume"}` |
| dense_interrupts | fixed_step@0.25s | 3 | `{"wall_at": 1.25, "phase": "LIVE", "game_remaining_before": 19.0, "game_remaining_after": 19.0, "note": "resume"}` | `{"wall_at": 1.2, "phase": "LIVE", "game_remaining_before": 19.0, "game_remaining_after": 19.0, "note": "resume"}` |
| dense_interrupts | fixed_step@0.25s | 4 | `{"wall_at": 1.5, "phase": "STOPPED", "game_remaining_before": 18.75, "game_remaining_after": 18.75, "note": "dense_pause_1"}` | `{"wall_at": 1.4, "phase": "STOPPED", "game_remaining_before": 18.8, "game_remaining_after": 18.8, "note": "dense_pause_1"}` |
| dense_interrupts | fixed_step@0.25s | 5 | `{"wall_at": 1.75, "phase": "LIVE", "game_remaining_before": 18.75, "game_remaining_after": 18.75, "note": "resume"}` | `{"wall_at": 1.6, "phase": "LIVE", "game_remaining_before": 18.8, "game_remaining_after": 18.8, "note": "resume"}` |
| dense_interrupts | fixed_step@0.25s | 6 | `{"wall_at": 2.0, "phase": "STOPPED", "game_remaining_before": 18.5, "game_remaining_after": 18.5, "note": "dense_pause_2"}` | `{"wall_at": 1.8, "phase": "STOPPED", "game_remaining_before": 18.6, "game_remaining_after": 18.6, "note": "dense_pause_2"}` |
| dense_interrupts | fixed_step@0.25s | 7 | `{"wall_at": 2.0, "phase": "LIVE", "game_remaining_before": 18.5, "game_remaining_after": 18.5, "note": "resume"}` | `{"wall_at": 2.0, "phase": "LIVE", "game_remaining_before": 18.6, "game_remaining_after": 18.6, "note": "resume"}` |
| dense_interrupts | fixed_step@0.25s | 8 | `{"wall_at": 2.25, "phase": "STOPPED", "game_remaining_before": 18.25, "game_remaining_after": 18.25, "note": "dense_pause_3"}` | `{"wall_at": 2.2, "phase": "STOPPED", "game_remaining_before": 18.4, "game_remaining_after": 18.4, "note": "dense_pause_3"}` |
| dense_interrupts | fixed_step@0.25s | 9 | `{"wall_at": 2.5, "phase": "LIVE", "game_remaining_before": 18.25, "game_remaining_after": 18.25, "note": "resume"}` | `{"wall_at": 2.4, "phase": "LIVE", "game_remaining_before": 18.4, "game_remaining_after": 18.4, "note": "resume"}` |
| dense_interrupts | fixed_step@0.25s | 10 | `{"wall_at": 2.75, "phase": "STOPPED", "game_remaining_before": 18.0, "game_remaining_after": 18.0, "note": "dense_pause_4"}` | `{"wall_at": 2.6, "phase": "STOPPED", "game_remaining_before": 18.2, "game_remaining_after": 18.2, "note": "dense_pause_4"}` |
| dense_interrupts | fixed_step@0.25s | 11 | `{"wall_at": 3.0, "phase": "LIVE", "game_remaining_before": 18.0, "game_remaining_after": 18.0, "note": "resume"}` | `{"wall_at": 2.8, "phase": "LIVE", "game_remaining_before": 18.2, "game_remaining_after": 18.2, "note": "resume"}` |
| dense_interrupts | fixed_step@0.25s | 13 | `null` | `{"wall_at": 3.2, "phase": "LIVE", "game_remaining_before": 18.0, "game_remaining_after": 18.0, "note": "resume"}` |
| dense_interrupts | fixed_step@0.25s | 14 | `null` | `{"wall_at": 3.4, "phase": "STOPPED", "game_remaining_before": 17.8, "game_remaining_after": 17.8, "note": "dense_pause_6"}` |
| dense_interrupts | fixed_step@0.25s | 15 | `null` | `{"wall_at": 3.6, "phase": "LIVE", "game_remaining_before": 17.8, "game_remaining_after": 17.8, "note": "resume"}` |
| dense_interrupts | fixed_step@0.25s | 16 | `null` | `{"wall_at": 3.8, "phase": "STOPPED", "game_remaining_before": 17.6, "game_remaining_after": 17.6, "note": "dense_pause_7"}` |
| dense_interrupts | fixed_step@0.25s | 17 | `null` | `{"wall_at": 4.0, "phase": "LIVE", "game_remaining_before": 17.6, "game_remaining_after": 17.6, "note": "resume"}` |
| dense_interrupts | fixed_step@0.25s | 18 | `null` | `{"wall_at": 4.2, "phase": "STOPPED", "game_remaining_before": 17.4, "game_remaining_after": 17.4, "note": "dense_pause_8"}` |
| dense_interrupts | fixed_step@0.25s | 19 | `null` | `{"wall_at": 4.4, "phase": "LIVE", "game_remaining_before": 17.4, "game_remaining_after": 17.4, "note": "resume"}` |
| dense_interrupts | fixed_step@0.25s | 20 | `null` | `{"wall_at": 4.6, "phase": "STOPPED", "game_remaining_before": 17.2, "game_remaining_after": 17.2, "note": "dense_pause_9"}` |
| dense_interrupts | fixed_step@0.25s | 21 | `null` | `{"wall_at": 4.8, "phase": "LIVE", "game_remaining_before": 17.2, "game_remaining_after": 17.2, "note": "resume"}` |
| dense_interrupts | fixed_step@0.25s | 22 | `null` | `{"wall_at": 5.0, "phase": "STOPPED", "game_remaining_before": 17.0, "game_remaining_after": 17.0, "note": "dense_pause_10"}` |
| dense_interrupts | fixed_step@0.25s | 23 | `null` | `{"wall_at": 5.2, "phase": "LIVE", "game_remaining_before": 17.0, "game_remaining_after": 17.0, "note": "resume"}` |
| dense_interrupts | fixed_step@0.25s | 24 | `null` | `{"wall_at": 5.4, "phase": "STOPPED", "game_remaining_before": 16.8, "game_remaining_after": 16.8, "note": "dense_pause_11"}` |
| dense_interrupts | fixed_step@0.25s | 25 | `null` | `{"wall_at": 5.6, "phase": "LIVE", "game_remaining_before": 16.8, "game_remaining_after": 16.8, "note": "resume"}` |
| dense_interrupts | fixed_step@0.25s | 26 | `null` | `{"wall_at": 5.8, "phase": "STOPPED", "game_remaining_before": 16.6, "game_remaining_after": 16.6, "note": "dense_pause_12"}` |
| dense_interrupts | fixed_step@0.25s | 27 | `null` | `{"wall_at": 6.0, "phase": "LIVE", "game_remaining_before": 16.6, "game_remaining_after": 16.6, "note": "resume"}` |
| dense_interrupts | fixed_step@0.25s | 28 | `null` | `{"wall_at": 6.2, "phase": "STOPPED", "game_remaining_before": 16.4, "game_remaining_after": 16.4, "note": "dense_pause_13"}` |
| dense_interrupts | fixed_step@0.25s | 29 | `null` | `{"wall_at": 6.4, "phase": "LIVE", "game_remaining_before": 16.4, "game_remaining_after": 16.4, "note": "resume"}` |
| dense_interrupts | fixed_step@0.25s | 30 | `null` | `{"wall_at": 6.6, "phase": "STOPPED", "game_remaining_before": 16.2, "game_remaining_after": 16.2, "note": "dense_pause_14"}` |
| dense_interrupts | fixed_step@0.25s | 31 | `null` | `{"wall_at": 6.8, "phase": "LIVE", "game_remaining_before": 16.2, "game_remaining_after": 16.2, "note": "resume"}` |
| dense_interrupts | fixed_step@0.25s | 32 | `null` | `{"wall_at": 7.0, "phase": "STOPPED", "game_remaining_before": 16.0, "game_remaining_after": 16.0, "note": "dense_pause_15"}` |
| dense_interrupts | fixed_step@0.25s | 33 | `null` | `{"wall_at": 7.2, "phase": "LIVE", "game_remaining_before": 16.0, "game_remaining_after": 16.0, "note": "resume"}` |
| dense_interrupts | fixed_step@0.25s | 34 | `null` | `{"wall_at": 7.4, "phase": "STOPPED", "game_remaining_before": 15.8, "game_remaining_after": 15.8, "note": "dense_pause_16"}` |
| dense_interrupts | fixed_step@0.25s | 35 | `null` | `{"wall_at": 7.6, "phase": "LIVE", "game_remaining_before": 15.8, "game_remaining_after": 15.8, "note": "resume"}` |
| dense_interrupts | fixed_step@0.25s | 36 | `null` | `{"wall_at": 7.8, "phase": "STOPPED", "game_remaining_before": 15.6, "game_remaining_after": 15.6, "note": "dense_pause_17"}` |
| dense_interrupts | fixed_step@0.25s | 37 | `null` | `{"wall_at": 8.0, "phase": "LIVE", "game_remaining_before": 15.6, "game_remaining_after": 15.6, "note": "resume"}` |
| dense_interrupts | fixed_step@0.25s | 38 | `null` | `{"wall_at": 8.2, "phase": "STOPPED", "game_remaining_before": 15.4, "game_remaining_after": 15.4, "note": "dense_pause_18"}` |
| dense_interrupts | fixed_step@0.25s | 39 | `null` | `{"wall_at": 8.4, "phase": "LIVE", "game_remaining_before": 15.4, "game_remaining_after": 15.4, "note": "resume"}` |
| dense_interrupts | fixed_step@0.25s | 40 | `null` | `{"wall_at": 8.6, "phase": "STOPPED", "game_remaining_before": 15.2, "game_remaining_after": 15.2, "note": "dense_pause_19"}` |
| dense_interrupts | fixed_step@0.25s | 41 | `null` | `{"wall_at": 8.8, "phase": "LIVE", "game_remaining_before": 15.2, "game_remaining_after": 15.2, "note": "resume"}` |
