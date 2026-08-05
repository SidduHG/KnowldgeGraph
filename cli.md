│
├── cli/                            ← Human control + Codex shell tool
│   ├── src/
│   │   ├── index.ts                ← Entry point, commander setup
│   │   ├── api/client.ts           ← Axios client wrapping backend REST
│   │   └── commands/
│   │       ├── index-cmd.ts        ← ckg index <path>
│   │       ├── watch-cmd.ts        ← ckg watch start/stop/status
│   │       ├── status-cmd.ts       ← ckg status
│   │       └── search-cmd.ts       ← ckg search <query>
│   ├── package.json
│   └── tsconfig.json