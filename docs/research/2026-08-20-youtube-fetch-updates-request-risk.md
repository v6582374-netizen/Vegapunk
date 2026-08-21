# Vegapunk YouTube「Fetch Updates」请求与风险核查

核查日期：2026-08-20  
范围：当前 `desktop/openworker/upstream/coworker/youtube/` 实现；只讨论用户手动点击 **Fetch Updates** 的网络行为与账号、配额、IP 风险。

## 结论

普通、合规的手动获取更新，首要风险不是“封 YouTube 账号”，而是两件更具体的事：

1. **YouTube Data API 项目日配额被字幕请求耗尽。** 当前每个待处理视频至少先调用一次 `captions.list`（50 units）；如果返回字幕轨道，还会逐轨调用 `captions.download`（200 units/次）。Google 明确要求 `captions.download` 的授权用户必须有权编辑该视频，因此它通常不适用于用户所订阅的第三方频道视频。[`captions.list`](https://developers.google.com/youtube/v3/docs/captions/list)；[`captions.download`](https://developers.google.com/youtube/v3/docs/captions/download)
2. **非官方字幕 fallback 可能触发出口 IP 封锁。** `youtube-transcript-api` 自己说明它调用 YouTube Web 客户端使用的未公开接口；请求过多时，自托管 IP 也可能收到 `RequestBlocked` 或 `IpBlocked`。当前 Vegapunk 没给这条路径附带 YouTube OAuth 凭据或 cookie，所以这个风险主要落在机器的出口 IP，而不是已连接的 YouTube 账号。[项目 README：IP blocks](https://github.com/jdepoix/youtube-transcript-api/blob/72d79711ec4db95262660029b4d63298b0820502/README.md#working-around-ip-bans-requestblocked-or-ipblocked-exception)；[项目 README：undocumented API warning](https://github.com/jdepoix/youtube-transcript-api/blob/72d79711ec4db95262660029b4d63298b0820502/README.md#warning)

达到正常配额上限时，YouTube Data API 文档定义的结果是 `403 quotaExceeded`；这与因违反 API 政策而暂停 API 凭据或 API Client 访问不是同一件事。官方条款允许 YouTube 对违规客户端暂停或终止 API 服务访问，并禁止绕过配额或 IP 限制，但没有把一次普通的 `quotaExceeded` 描述为 YouTube 用户账号封禁。[API errors](https://developers.google.com/youtube/v3/docs/errors)；[API Services Terms §15](https://developers.google.com/youtube/terms/api-services-terms-of-service#usage-and-quotas)；[Developer Policies: Usage and Quotas](https://developers.google.com/youtube/terms/developer-policies#usage-and-quotas)

## 当前一次 Fetch Updates 实际做什么

| 阶段 | 触发条件 | 当前请求 | 身份与配额 | 主要风险 |
| --- | --- | --- | --- | --- |
| 授权有效性 | 每次点击 | 读取本地 access token；临近过期时向 Google OAuth token endpoint 刷新 | 使用本地 refresh token；不是 YouTube Data API 方法，不计 Data API units | token 被撤销或失效时本次扫描直接失败 |
| 同步订阅 | 本地还没有频道时 | `subscriptions.list(mine=true, maxResults=50)`，逐页读取 | OAuth；每页 1 unit | 很低；例如 500 个订阅约 10 units |
| 发现更新 | 每次点击、每个本地频道 | `GET https://www.youtube.com/feeds/videos.xml?channel_id=…` | 公开 RSS，无 API key/OAuth；不属于 Data API 方法，因此不消耗 Data API units | 高频或高并发时可能遇到普通 HTTP 限流；Google 没公布该 feed 的安全请求频率 |
| 查字幕轨道 | 每个新视频，以及历史 `pending`/`error` 视频 | `captions.list(videoId=…)` | OAuth；50 units/视频/次 | 日配额消耗；错误视频会在以后每次点击时重试 |
| 下载官方字幕 | `captions.list` 返回轨道时 | 按语言优先级逐条 `captions.download(tfmt=vtt)`，直到成功或全部失败 | OAuth；200 units/轨道/次；调用者必须有权编辑视频 | 对订阅的第三方视频通常没有权限，形成高成本的失败请求 |
| 非官方 fallback | 官方字幕路径未得到正文时 | `youtube-transcript-api.list(video_id)` 后选择一条轨道并 `fetch()` | 当前无 OAuth、cookie 或代理；调用未公开的 Web 客户端接口 | YouTube 变更即可能失效；频繁请求可能封出口 IP |

本表对应当前代码：[`service.py`](../../desktop/openworker/upstream/coworker/youtube/service.py) 的扫描、RSS 循环和错误重试，以及 [`client.py`](../../desktop/openworker/upstream/coworker/youtube/client.py) 的订阅分页、官方字幕和 `youtube-transcript-api` fallback。当前 YouTube 路径不使用 `yt-dlp`。

## 点击频率如何转化为负载

设：

- `C` = 本地订阅频道数；
- `P` = 首次同步订阅的分页数，约为 `ceil(订阅数 / 50)`；
- `V` = 本次新视频与历史待重试视频总数；
- `Tᵢ` = 第 `i` 个视频实际尝试下载的官方字幕轨道数。

则一次扫描大致产生：

- 常规发现：`C` 次 RSS HTTP GET；
- 仅在本地频道为空时：`P` 次 `subscriptions.list`，消耗 `P` units；
- 字幕：`Σ(50 + 200 × Tᵢ)` units，外加每个未成功视频的一次 `youtube-transcript-api` fallback 操作。

Google 当前文档给 YouTube Data API 项目的默认额度为每天 10,000 units（`search.list` 和 `videos.insert` 有各自单独默认桶；这里涉及的方法属于其余 endpoints），并说明所有 API 请求，包括无效请求，至少产生配额成本；额外分页也按页计费。默认额度可能变化，实际值应以 Google Cloud Console 为准。[Quota overview](https://developers.google.com/youtube/v3/getting-started#quota)；[Quota cost table](https://developers.google.com/youtube/v3/determine_quota_cost)

因此，在“一条官方轨道被列出，但下载因无编辑权限而失败，随后走 fallback”的情况下，一个视频约占 `50 + 200 = 250` units；40 个这样的视频就能用完 10,000 units。若每个视频尝试两条轨道，则约 450 units/视频，约 22 个视频就接近上限。这里最值得担心的不是用户多点了几次 RSS，而是**失败字幕被每次扫描重复执行昂贵的官方调用**。

如果没有新视频，也没有 `pending`/`error` 字幕，频繁点击主要只是重复 `C` 个公开 RSS 请求，通常不会消耗 YouTube Data API 配额；但仍不应并发或秒级刷取，因为 RSS 没有公布的请求频率保证。

## “封号”、配额与限流是三个不同边界

### 1. 普通配额耗尽

官方错误定义是 `403 quotaExceeded`，影响的是该 Google Cloud API Project 在额度恢复或提升前继续调用 API。文档没有说普通达到配额会暂停用户的 YouTube 账号。[YouTube Data API errors](https://developers.google.com/youtube/v3/docs/errors)

### 2. 短时间请求过多

Data API 也定义了 `rateLimitExceeded`，含义是用户在给定时间窗口内发送了过多请求。这是请求失败/限流语义，不等同于账号封禁；官方没有公布一个可承诺“绝对安全”的手动点击次数。[YouTube Data API errors](https://developers.google.com/youtube/v3/docs/errors)

公开 RSS 没有 OAuth 身份，`youtube-transcript-api` 当前也没有账号 cookie；这两类请求出现限制时，更可能体现为 HTTP 错误或出口 IP 被挡。`youtube-transcript-api` 的 README 明确提到自托管环境请求过多也可能触发 IP block。[项目 README](https://github.com/jdepoix/youtube-transcript-api/blob/72d79711ec4db95262660029b4d63298b0820502/README.md#working-around-ip-bans-requestblocked-or-ipblocked-exception)

### 3. 政策违规或绕过限制

这不是“请求多了一点”的同义词。YouTube API 条款禁止试图超过或绕过配额限制；Developer Policies 也禁止规避 YouTube 施加的 IP/地域限制。违规时，YouTube 可以暂停或终止 API Services、API credentials 或 API Client 的访问。[API Services Terms §3.1](https://developers.google.com/youtube/terms/api-services-terms-of-service#permitted-access)；[API Services Terms §15](https://developers.google.com/youtube/terms/api-services-terms-of-service#usage-and-quotas)；[Developer Policies](https://developers.google.com/youtube/terms/developer-policies)

所以即使 `youtube-transcript-api` README 提供了代理规避 IP block 的办法，Vegapunk 也不应默认接入“被封后自动换代理继续抓取”这类机制；这会把一个可靠性问题升级为明确的合规风险。

## 对当前实现的最小改进建议

1. **停止为第三方频道视频调用 `captions.download`。** 它的官方权限边界与“读取订阅频道视频”不匹配。只有视频属于已连接账号、用户确实有编辑权限时才走官方 `captions.list/download`；其他视频直接进入受控 fallback。
2. **不要让同一个字幕错误在每次 Fetch Updates 都立即重试。** 为 `pending/error` 设置按视频退避和 `next_retry_at`，字幕不可用与临时网络失败采用不同重试周期。
3. **扫描单飞。** 前端按钮和后端同时阻止同一时刻启动多个扫描；紧邻点击复用正在进行的结果。
4. **字幕获取应按用户选择执行。** “Fetch Updates”只发现视频；用户选择后才取字幕。这最符合当前产品边界，也同时减少配额、IP 请求和无意义失败。
5. **对 403/429 停止而不是绕过。** 显示“配额耗尽”或“请求受限”，按退避策略恢复；不自动轮换代理。

## 一手来源

- [YouTube Data API: `subscriptions.list`](https://developers.google.com/youtube/v3/docs/subscriptions/list)
- [YouTube Data API: `captions.list`](https://developers.google.com/youtube/v3/docs/captions/list)
- [YouTube Data API: `captions.download`](https://developers.google.com/youtube/v3/docs/captions/download)
- [YouTube Data API quota overview](https://developers.google.com/youtube/v3/getting-started#quota)
- [YouTube Data API quota cost table](https://developers.google.com/youtube/v3/determine_quota_cost)
- [YouTube Data API errors](https://developers.google.com/youtube/v3/docs/errors)
- [YouTube API Services Terms of Service](https://developers.google.com/youtube/terms/api-services-terms-of-service)
- [YouTube API Services Developer Policies](https://developers.google.com/youtube/terms/developer-policies)
- [`youtube-transcript-api` README, pinned revision](https://github.com/jdepoix/youtube-transcript-api/blob/72d79711ec4db95262660029b4d63298b0820502/README.md)
