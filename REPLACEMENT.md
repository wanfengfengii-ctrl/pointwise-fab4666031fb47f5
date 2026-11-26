# 展次内单屏换机

现有派画、交件、发拍和实显接口见 `README.md`。样例展次 `gallery-day` 的左屏是 `panel-L`，右屏是 `panel-R`。换机演练使用备用设备 `panel-spare`。

## 登记和续查

向 `POST /screen-replacements` 提交 JSON。

```json
{
  "session_id": "gallery-day",
  "position": "left",
  "replacement_screen_id": "panel-spare",
  "activation_pulse": 10,
  "request_id": "replace-left"
}
```

成功返回 HTTP 200，响应含原请求五个字段，以及正整数 `replacement_id`、`status` 和 `activated_pulse`。登记后 `status` 为 `pending`，`activated_pulse` 为 `null`。启用后分别为 `active` 和实际启用拍号。`GET /screen-replacements/{replacement_id}` 返回同样的记录。

设备号、展次、屏位及请求号沿用现有可打印字符串规则。计划拍和现有发拍使用相同的非负整数范围。首次登记时，计划拍必须晚于展次内已处理的最大拍号。每展次只能安排一次换机，备用设备号必须在该展次内未用。同展次同请求号同参复领同一换机号和当前状态。同请求号改参、已有另一份换机安排、设备号已用或计划拍已过，返回 409。未知展次、屏位、换机号返回 404，坏参数返回 400。错误响应仍用 `error`。

## 启用和出屏

登记后照常在原设备接件和出屏。首个达到计划拍的新拍，以该拍号启用备用设备。发拍的同一次提交中承接原设备实际持有的前画和备画，有备画则用备画推进，空备则沿用前画。启用拍在 `screens` 中使用接替设备号。只要接替屏实际显示了画面，当拍 `shown` 和历史都记录该设备及实际采用的画面，即使采用的是承接来的前画。两槽皆空则当拍没有该屏位的实显。其他屏正常推进。启用之后的普通空备拍仍只记录拍后快照。

`GET /sessions/{session_id}` 的屏位布置和 `GET /sessions/{session_id}/screens/{position}` 的前画查询从启用拍起反映接替设备。复投已处理拍始终复领最初结果。按屏位查询历史时，应同时查得到原设备和接替设备的实显，各行保留当拍设备、派单、画面和原有出处。

## 旧单和继续派画

存量派单仍可按原 `dispatch_id` 查询，返回的 `screen_id` 保留登记时的设备。原设备已经真实装过的交件，原路重投只回原确认，哪怕该件已经离开槽位。原回包晚到仍可确认同一派单，且不会改变前画或备画。

尚未实装的原单在换机后只能由接替设备首次接纳。按原 `request_id`、屏位和画面再次 `POST /dispatches`，沿用同一派单号，交件送到接替设备。原设备在途的完整旧交件在启用后到达原入口时返回 409，且不改变槽位与确认。接替设备真实装载的确认可确认该原单。新派画使用当前设备。正常的同号异参、画面核验及原路重复交件规则继续适用。

## 演练

`samples.replacement_setup.prepare(case)` 通过现有测试端口备好三幅画、9 拍回执、B 的待回确认和仍在途的 C 交件。`python3 -B -m samples.replacement_setup` 可重跑换机前的接件和发拍行为。

`python3 -B -m samples.replacement_drill` 用真实 HTTP 端口跑三段演练，各自临时库与动态端口，末行输出经断言核对的 `POINTWISE_SCENARIO` JSON：

1. `replacement-boundary`：同一输入登记第10拍换机。C 仍在途时，左屏第9拍查到 `panel-L` 的 A，第10拍查到 `panel-spare` 的 B。把 C 的旧件送给 `panel-L` 得 409。按原请求续送 C 到乙后补交 B 的原回包，第11拍由 `panel-spare` 显示原单 C，B 补确认不改槽。随后重开服务，复查换机记录、原派单号与其 `screen_id`、布置、实显与出处，并复投第9、10拍核对原结果。`deliveries` 记下拍界前发给甲的 A、B 和拍界后重发到乙的 C，`visible_front_by_pulse` 记下第10、11拍的实际前画。
2. `replacement-skip`：空备时直接从第9拍跳到第12拍，换机记录的实际启用拍是12，乙在第12拍显示沿用的 A。
3. `replacement-early`：C 在启用拍之前先到甲，第10拍由乙显示 C，原装载确认仍归甲。

保留 `python3 -B check_project.py` 的原回归；该入口先跑完整套件，再跑同一段换机演练，任一步失败返回非零。使用 `.pointwise-runtime.json` 登记服务启动及换机核验、业务演示。清单用版本 1 的 API 运行方式，准备步骤是参数数组列表，可以为空。启动、核验、演示各为一个命令参数数组。服务仅监听 `127.0.0.1`，就绪检查沿用展次查询。核验失败时返回非零退出码。
