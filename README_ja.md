# Outline をローカルで運用する

[English](README.md) | 日本語

Outlineと依存で必要なPostgreSQL、Redis、Dex を Docker Compose で起動します。
Outlineのユーザ認証には Dex を使い、ユーザーは `dex/users.env`に保存します。

| 用途 | URL |
| --- | --- |
| Outline | `http://localhost:3000` |
| Dex ログイン | `http://localhost:5556/dex` |


## データの保存場所


| ディレクトリ | 内容 |
| --- | --- |
| `data/postgres/` | PostgreSQL の DB 一式（18 系の `18/docker/` を含む） |
| `data/dex/` | Dex の SQLite・署名鍵など |
| `data/outline/` | 文書の添付ファイル |
| `data/redis/` | Redis の永続データ |

なお，上記データファイルの所有者は UID:1001/GID:1001 になるため、ホストでのコピーには `sudo` が必要な場合があります。


## 初期設定

Docker、Docker Compose、Python をインストールしてください。
また，ホストの TCP 3000 / 5556 を使用するため、他のプログラムが使用しないようにしてください。

1. 設定ファイルを編集します
```sh
cp .env.example .env
chmod 600 .env
```

`.env` の `POSTGRES_PASSWORD`、`SECRET_KEY`、`UTILS_SECRET` に、それぞれ `openssl rand -hex 32` で生成した別々の値を設定してください。

2. 最初のローカルユーザーを設定します。

```sh
python3 scripts/dex-users.py add user@example.com --name "名前" --no-apply
```

パスワードはコマンド実行時に端末で入力してください。
また，メールアドレスはユーザーの識別のためだけ使い、メール認証等は行いません。


## ユーザー管理
```sh
# 一覧
python3 scripts/dex-users.py list
# 追加
python3 scripts/dex-users.py add alice@example.com --name "Alice"
# パスワード変更
python3 scripts/dex-users.py passwd alice@example.com
# 削除
python3 scripts/dex-users.py delete alice@example.com
```

* 追加・パスワード変更・削除では、一時的に認証サービスを停止します。
* 最後の1ユーザーは削除できません。
* Outlineでのユーザ追加は新しいユーザーの初回ログイン時に行われます。
* 参加させたいワークスペースへの招待・権限設定は Outline 側で行ってください。
* Dex でのユーザ削除では、Outline上のユーザは削除されません。削除には Outline の **Settings → Users** でも対象ユーザーを削除してください。
* `--no-apply` を付けると、Dex の再起動を行いません。変更をまとめて行ったあと、`apply` を実行することでまとめて変更が反映されます。
```sh
python3 scripts/dex-users.py add alice@example.com --name "Alice" --no-apply
python3 scripts/dex-users.py add bob@example.com --name "Bob" --no-apply
python3 scripts/dex-users.py apply
```


## 起動・ログイン
```sh
docker compose up -d
```

`http://localhost:3000` を開き、**Local account** を選んで、スクリプトで設定したメールアドレス・パスワードでログインします。初めて使う場合は Outline の案内に従ってワークスペースを作成します。


## 更新

`.env` の `OUTLINE_VERSION` または `DEX_VERSION` を更新し、`docker compose pull` と `docker compose up -d` を実行します。
ただし、DB マイグレーションが行われると、イメージを戻すだけではデータが復旧できない場合があります。
このため、更新の前にデータのバックアップを推奨します。


## 参考

- [Outline OIDC 設定](https://docs.getoutline.com/s/hosting/doc/oidc-8CPBm6uC0I)
- [Dex ローカルユーザー](https://dexidp.io/docs/connectors/local/)
- [Dex ストレージ](https://dexidp.io/docs/configuration/storage/)
- [Dex 公式 Docker 設定](https://github.com/dexidp/dex/blob/v2.46.1/config.docker.yaml)
