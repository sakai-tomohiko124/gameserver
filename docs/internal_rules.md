# 内部ルール（非公開） — 大富豪カスタムルール集

この文書はサーバ実装で用いられる特別ルールのまとめです。UI上には表示されません。

| ルール | 説明 | 実装箇所（サーバ） | 備考 |
|---|---|---:|---|
| 4/A のダブル（2枚）で即時ランク回転 | 4が2枚、またはAが2枚で特定の順位回転（大富豪が大貧民へ等）を適用 | `rooms._apply_instant_grade_rotation` | 実行時に `instant_grade_rotation` イベントを emit |
| 5 | 次の人を1回スキップ | `play_card` の `contains_5` ハンドリング | 追加で `_advance_to_next_active` を呼ぶ |
| 7 | 1枚カードを渡す（give） | `play_card` と `give_card` の `pending_give` フロー | 受け渡しは `give_card` API 経由 |
| 8（八切り） | 場を流す | `play_card` の `contains_8` ハンドリング | ただし場に2が含まれる場合は例外（下記参照） |
| 9 | 全カードをシャッフル（ハンズシャッフル） | `play_card` の `contains_9` → `rooms._shuffle_hands` | |
| 10 | 出したら1枚捨てる（任意） | `play_card` の `contains_10` → `pending_discard` | ボットは自動で数秒後に捨てる処理あり |
| J（ジャック） | 革命（revolution）をトグル | `play_card` の `contains_J` | `room['revolution']` をトグル、`_rank_greater` が参照 |
| Q | 指定ランクを全員が持っていたら全て捨てる（mass discard） | `play_card` の `contains_Q` と `target_rank` | `mass_discard` イベントを emit |
| K | 進行方向を反転（時計⇄反時計） | `play_card` の `contains_K` | `room['direction']` を反転 |
| 2 | 強いカード（高ランク） | `_rank_value` / `_rank_index_from_rank` の順位 | Joker より下の扱い（Joker を最強とする現挙動） |
| Joker | ワイルド（ワイルドとして扱える）・最強扱い | `_play_meta`, `_rank_value` で JOKER を特別扱い | 現在は Joker が最強（999） |
| スペードの3がJokerより強い（特例） | （実装済みであればここにバージョン） | `rooms._rank_special_cases`（想定） | ※ UI には記載しない |
| 2 の後の 8 の制限 | 場に 2 が含まれる場合、8 は Joker を含む手以外許可しない | `rooms._allowed_play_against` | 人間は Joker を持っていなければ自動でパス（RoomMonitor） |


## 備考
- 上のルールはサーバ内部で処理されます。クライアントの表示や説明文は変更していません（要望どおり、ルール文は非表示）。
- 将来的にルールを部屋ごとに切り替えられるようにすることができます（要望があれば追加します）。
