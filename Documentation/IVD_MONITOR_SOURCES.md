# IVD Monitor Regulatory & Financial Sources

This document outlines the collectors implemented for the IVD monitor and the
operational guidance for each upstream source. Use this as the authoritative
reference when running or extending collectors.

## Financial Disclosures

### CNInfo / 巨潮资讯 (financial.cninfo_juchao)

* **Source type:** `financial_reports`
* **Endpoint:** `https://www.cninfo.com.cn/new/hisAnnouncement/query`
* **Query parameters:**
  - `pageNum`: 1-based page index (required)
  - `pageSize`: page size, defaults to 30 (required)
  - `seDate`: date range in `YYYY-MM-DD~YYYY-MM-DD` format (required)
  - `column`, `plate`, `sortName`, `sortType`, `token`: use defaults defined in the
    collector unless searching for specific boards or categories
* **Pagination:** numeric pages, descending by publish time
* **Rate limits:** the public API responds best with 5 requests per second or
  slower; enforce a 200&nbsp;ms delay between page fetches when crawling
* **Fallback strategy:** if the JSON endpoint changes, fall back to the full text
  search page (`/new/fulltextSearch`) or HTML listings. The collector already
  normalises timestamps and handles document metadata such as `adjunctType` and
  `announcementId`.

### Shanghai Stock Exchange (financial.shanghai_exchange)

* **Source type:** `financial_reports`
* **Primary endpoint:** `https://query.sse.com.cn/infodisplay/queryLatestBulletinNew.do`
* **Query parameters:**
  - `pageHelp.pageNo`: requested page (1-based)
  - `pageHelp.pageSize`: page size (default 25)
  - `productId`, `keyWord`: optional filters, leave empty for global feed
* **Pagination:** JSON response contains `pageHelp.pageCount`; the collector stops
  automatically when no more pages remain
* **Rate limits:** 3–4 requests per second are accepted; use the configured
  300&nbsp;ms delay between page fetches
* **Fallback strategy:** when JSON parsing fails, parse HTML from
  `https://www.sse.com.cn/disclosure/listedinfo/announcement/`. The HTML parser
  extracts titles, URLs, and publish dates from list items.

### Shenzhen Stock Exchange (financial.shenzhen_exchange)

* **Source type:** `financial_reports`
* **Endpoint:** `https://www.szse.cn/api/disc/announcement/annList`
* **Query parameters:**
  - `channelCode`: e.g. `listedNotice_disc`
  - `seDate`: date range `YYYY-MM-DD~YYYY-MM-DD`
  - `pageNum`: 0-based page index
  - `pageSize`: page size (default 30)
* **Pagination:** uses zero-based page numbering; the response contains
  `totalCount` for page calculations
* **Rate limits:** limit to 3 requests per second; introducing a 300&nbsp;ms delay
  avoids throttling
* **Fallback strategy:** scrape the HTML disclosure listings under
  `https://www.szse.cn/disclosure/listed/notice/` when the API schema changes or
  is unavailable.

## Regulatory Sources

### National Medical Products Administration (regulatory.nmpa_approvals)

* **Source type:** `product_launches`
* **Endpoint:** `https://www.nmpa.gov.cn/data/i/v1/medicalDevice/registration`
* **Query parameters:**
  - `page`: 1-based page index
  - `size`: page size (default 20)
  - `sort`: set to `-issueDate` for newest approvals first
  - `searchText`: optional keyword filter
* **Pagination:** uses `total` in the response for overall count
* **Rate limits:** keep request rate below 2 per second; configured delay is
  500&nbsp;ms
* **Fallback strategy:** parse HTML listings from `https://www.nmpa.gov.cn/xxgk/ggtg/ylqx/`
  when JSON responses are unavailable. The collector already includes an HTML
  parser that extracts titles and dates.

### National Healthcare Security Administration (regulatory.nhsa_policy)

* **Source type:** `reimbursement_policy`
* **Primary access:** HTML listings under `https://www.nhsa.gov.cn/col/col5881/`
* **Pagination:** sequence of `index.html`, `index_1.html`, `index_2.html`, etc.
  The collector paginates until fewer than `page_size` items are returned
* **Rate limits:** do not exceed 2 requests per second; a 400&nbsp;ms delay is
  recommended
* **Fallback strategy:** inspect the HTML for structural changes. Selectors in
  use: `ul.list-box li`, `li.list-item`. Capture archive snapshots when the site
  changes to update tests quickly.

### National Health Commission (regulatory.nhc_notices)

* **Source type:** `health_commission_policy`
* **Primary access:** HTML listings under
  `https://www.nhc.gov.cn/guihuaxxs/s10742/s14680/`
* **Pagination:** `index.shtml` for page 1, `index_1.shtml` for page 2, etc.
* **Rate limits:** target 2 requests per second with a minimum 400&nbsp;ms delay
* **Fallback strategy:** the HTML parser falls back to broad selectors (`.list li`)
  to accommodate layout updates. If deeper changes occur, switch to the official
  search endpoint at `https://search.nhc.gov.cn/search/`.

## Testing Notes

* All collectors output `RawRecord` instances with UTC-normalised publish dates
  and source categories used by downstream enrichment.
* Fixtures (`tests/ivd_monitor/sources/fixtures`) contain representative JSON and
  HTML samples with Chinese text. Extend them when upstream schemas change.
* Unit tests validate multi-page handling, timezone conversion, and metadata
  extraction. Run `pytest tests/ivd_monitor/sources` after modifying collectors or
  updating fixtures.
