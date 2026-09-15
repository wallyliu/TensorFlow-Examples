# 把圖案騎出來

給一個形狀，在真實可騎的道路上找出一條看起來像它的單車路線，輸出成車機吃得下的 GPX。

```bash
pip install -r requirements.txt
python server/app.py          # http://127.0.0.1:8000
```

第一次在某個地點算路線會先下載該區路網（幾分鐘），之後存在硬碟不再下載。
想先把整個北部抓下來（可中斷續傳）：

```bash
python -m routeshape.region.download --region north --mode bike --near 25.04,121.54
```

## 這個 repo 怎麼分

| 目錄 | 是什麼 |
|---|---|
| `routeshape/` | **產品**。server 用到的全部在這裡，而且不依賴 `experiments/` 的任何東西。 |
| `server/` | HTTP 服務（純標準函式庫）和網頁 |
| `experiments/` | 51 個 POC 腳本。每一個常數都是這裡量出來的，留著是為了可以回頭查證。 |
| `docs/` | `BACKLOG.md`（還沒解決的事）和各輪 POC 的說明 |
| `results/` | 實驗產出的圖和量測數據 |
| `gpx/` | 匯出的路線 |

`routeshape/` 裡面：

    network      下載並快取路網
    placement    把形狀放到地圖上、建街道索引、挑候選中心
    search       粗篩擺放位置，再細擬合
    matching     Viterbi 圖資比對，把錨點變成路線
    feasibility  距離買得到什麼：n_min、寬度、繞路、最低距離
    recognition  有多少人認得出這個形狀（POC 29 實測）
    street_scale 這個地點的街道有多疏（POC 26 實測）
    metrics      形狀距離、轉正角度
    wander       路線比輪廓長多少
    export       GPX
    describe     一段敘述 → 一個輪廓，用完之前先驗過
    shapes/      圖案庫
    region/      分塊地圖快取

## 幾個量出來的數字

- **形狀距離 0.10** 是人「看得出兩張圖不一樣」的門檻，不是「認得出這是什麼」。
- **辨識門檻每個形狀不一樣**：三角形 0.120、月亮 0.166、恐龍 0.169、愛心 0.286、五角星 0.321。四個標註者、120 筆判斷。
- **繞路係數不是常數**，隨圖案尺寸和當地街道疏密變化。
- 詳細情形和還沒解決的問題在 `docs/BACKLOG.md`。
