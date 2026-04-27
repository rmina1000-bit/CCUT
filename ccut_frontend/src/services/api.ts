/**
 * CCUT Central API Gateway
 */

export const API_BASE_URL = "/api";

export const fetcher = async (path: string, options?: RequestInit) => {
    const url = `${API_BASE_URL}${path}`;
    const res = await fetch(url, {
        ...options,
        headers: {
            "Content-Type": "application/json",
            ...options?.headers,
        },
    });
    if (!res.ok) throw new Error(`Engine Error: ${res.statusText} (${res.status})`);
    return res.json();
};