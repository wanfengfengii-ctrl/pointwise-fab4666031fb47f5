# 市民科技馆展陈播控

内容员把素材表中的整数 RGB 图制成两侧固定校样。值班员按展次屏位逐屏排画并发拍。展务员以实显记录核对观众在当时看到的画面。素材改版后，原来的幕单和旧拍仍可追查。

## 运行

需要 Python 3.11 和标准库。从项目根目录执行：

```sh
python3 -B -m desk.server --db gallery.sqlite3 --port 8000
python3 -B check_project.py
python3 -B -m samples.workday
```

服务监听 `127.0.0.1`。`--seed` 可指定首次启动所用的展次 JSON，默认读取 `samples/session.json`。空库在一次事务内写入展次、屏位和空槽。启动已有库保留原布置、素材、派单、槽位和旧拍。演示使用自己的临时库及动态端口，输出经断言核对的 `POINTWISE_SCENARIO` JSON。

## 工作日请求

成功响应为 HTTP 200。请求用 JSON。下表以样例展次 `gallery-day` 和屏位 `left`、`right` 举例。画面、修订、幕单及派单号为正整数。拍号是非负整数，数值字段须在 SQLite 有符号整数范围内。错误响应为 `{"error": "说明"}`。

| 步骤 | 接口与输入 | 结果 |
| --- | --- | --- |
| 1. 领布置 | `GET /sessions/gallery-day` | 展次名称及按顺序列出的 `placements`，含 `position`、`screen_id`、`name`、`ordinal` |
| 2. 固定原图 | `POST /artwork`，`{"art_id":"orbit","pixels":[[[255,0,0],[0,255,0]],[[0,0,255],[255,255,0]]]}` | `revision_id`、`art_id`、`width`、`height`。`GET /artwork/{revision_id}` 同时返回 `pixels` |
| 3. 制幕 | `POST /sheets`，`{"revision_id":1,"left":[0,0,1,2],"right":[1,0,2,2]}` | `sheet_id`、`left_frame_id`、`right_frame_id` |
| 4. 核校样 | `GET /sheets/{sheet_id}` | `sheet_id`、`art_id`、`revision_id`、`left` 及 `right` 画面。每侧返回画面号、幕单号、修订、侧别、视口、宽高及像素 |
| 5. 派画 | `POST /dispatches`，`{"session_id":"gallery-day","position":"left","frame_id":1,"request_id":"morning-left"}` | 原 `dispatch_id`、固定屏位和逻辑屏、画面、请求号及 `status`。`GET /dispatches/{dispatch_id}` 可按号续查 |
| 6. 送达 | `POST /screens/panel-L/loads`，见下文交件格式 | 返回装载确认。`GET /sessions/gallery-day/screens/left` 可读当下前槽及其实际像素，空前槽返回 `null` |
| 7. 发拍 | `POST /pulses`，`{"session_id":"gallery-day","pulse":10}` | `session_id`、`pulse`、各屏拍后 `screens` 和本拍实际采用的 `shown` |
| 8. 复盘 | `GET /sessions/gallery-day/shown`，可附 `?position=left` | 按数值拍号和布置顺序返回实显数组，附原图号、修订、幕单、侧别及原视口 |

视口按 `[x0,y0,x1,y1]` 提交。坐标零基，x 向右、y 向下，下界包含、上界排除。每侧必须完整落在原图中且面积非零。裁切保留原行顺序及 RGB。示例左列由红、蓝构成，右列由绿、黄构成。非法像素或视口返回 400。未知原图修订、幕单、派单、展次或查询屏位返回 404。任一视口失败时本次幕单的两侧均未签出。

默认本地端口在派单登记提交后，向对应屏送达一份交件。在装载提交后，匹配的墙端回包让派单从 `pending` 变为 `confirmed`。交件包含 `dispatch_id`、`session_id`、`position`、`screen_id`、`frame_id`、`revision_id`、`width`、`height` 和 `pixels`。墙端回包包含 `dispatch_id`、`session_id`、`screen_id`、`frame_id`、`revision_id`。同一展次内同号同参可重领原单，同号异参返回 409。内容损坏返回 400，完整交件送错入口返回 409。两种失败均保留备槽。

一个屏有一个实际前槽和一个备槽。新的合法交件按首次接收顺序更新备槽。原交件重送只复领装载确认。值班员可用新请求号再次排入同一固定画面。发拍逐屏消费实际备槽，空备槽沿用旧前槽。每次真实采用留下实显，单纯维持原画的拍点只存拍后快照。重投已见拍始终返回原快照及原新增项，未见的更早拍号返回 409。合法范围内无实显时返回 `[]`。

## 核验

完整套件从 `tests` 发现。`tests/test_preparation.py` 检查逐像素裁切及坏件拒绝。`tests/test_playout.py` 通过实际 HTTP 送达，检查独立槽、补确认及保护既有备槽。`tests/test_shown_history.py` 核对原拍重领、出处和重开。`tests/test_startup.py` 验证初始化回滚与重启。`tests/test_workday.py` 验证拍点异常回滚和展次隔离。`tests/test_replacement.py` 覆盖单屏换机的登记、启用承接、旧单续送与重开；演练见 `REPLACEMENT.md`。`build_application` 可接收 `send_load` 和 `send_receipt` 回调，供本地端口分别暂扣交件或回包。测试通过同一 HTTP 入口送件和推进拍号。
