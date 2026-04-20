module github.com/ai-platform/platform

go 1.21

replace github.com/ai-platform/platform/proto/chat => ./proto/chat

require (
	github.com/ai-platform/platform/proto/chat v0.0.0-00010101000000-000000000000
	github.com/golang-jwt/jwt/v5 v5.2.0
	github.com/google/uuid v1.5.0
	github.com/gorilla/websocket v1.5.1
	github.com/jackc/pgx/v5 v5.5.1
	github.com/redis/go-redis/v9 v9.3.0
	golang.org/x/crypto v0.17.0
	google.golang.org/grpc v1.60.0
)

require (
	github.com/cespare/xxhash/v2 v2.2.0 // indirect
	github.com/dgryski/go-rendezvous v0.0.0-20200823014737-9f7001d12a5f // indirect
	github.com/golang/protobuf v1.5.3 // indirect
	github.com/jackc/pgpassfile v1.0.0 // indirect
	github.com/jackc/pgservicefile v0.0.0-20231201235250-de7065d80cb9 // indirect
	github.com/jackc/puddle/v2 v2.2.1 // indirect
	golang.org/x/net v0.19.0 // indirect
	golang.org/x/sync v0.5.0 // indirect
	golang.org/x/sys v0.15.0 // indirect
	golang.org/x/text v0.14.0 // indirect
	google.golang.org/genproto/googleapis/rpc v0.0.0-20231212172506-995d672761c0 // indirect
	google.golang.org/protobuf v1.31.0 // indirect
)
