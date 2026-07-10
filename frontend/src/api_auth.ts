export async function authSignup(payload: any): Promise<any> {
  const url = '/auth/signup';
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const errorData = await response.json().catch(() => null);
    throw new Error(errorData?.detail || 'Signup failed');
  }
  return response.json();
}
