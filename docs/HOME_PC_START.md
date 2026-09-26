# 帰宅後の最短手順 — v0.3

## 1. ZIPを展開
`C:\AI-App-Platform` など分かりやすい場所へ展開。

## 2. `START_HERE.bat`
ダブルクリック。

Pythonが無いと言われた場合だけ `SETUP_WINDOWS.bat` を開く。
Python 3.11以上が入ればOK。`python` コマンドが無くても Windows の `py` ランチャーに対応済み。

## 3. 起動後の確認
1. `＋ 新規プロジェクト`
2. 例: `ログイン付き予約アプリをWebとAndroid向けに作って`
3. `Safety Check → 仕様化 → 制作 → テスト`
4. 結果欄で App type / features / targets / PASS を確認
5. `ローカルプレビュー`
6. `保守スキャン`

## 4. 全体テスト
`RUN_TESTS.bat`

開発環境で15テストPASS済み。自宅PCでも同じ結果になるか確認する。

## 5. Windowsパッケージ試験
`build_windows.bat`
初回のみPyInstallerの取得にインターネット接続が必要。

## まだ入力しないもの
- クラウドAPIキー/秘密鍵
- カード情報
- 本番DB情報

v0.3では本番接続を意図的に無効化している。
