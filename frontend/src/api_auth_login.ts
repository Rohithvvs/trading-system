export async function authLogin(payload: any): Promise<any> {
  const url = '/auth/login';
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const errorData = await response.json().catch(() => null);
    throw new Error(errorData?.detail || 'Login failed');
  }
  return response.json();
}
