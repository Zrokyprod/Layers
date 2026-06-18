export interface ZrokyActionConfig {
    raw?: string;
    runner?: {
        command?: string;
        timeoutSeconds?: number;
    };
    replay?: {
        toolMode?: string;
        trials?: number;
    };
    contracts?: {
        include: string[];
    };
}
export declare function loadZrokyConfig(configPath: string): Promise<ZrokyActionConfig>;
export declare function parseZrokyYaml(raw: string): ZrokyActionConfig;
