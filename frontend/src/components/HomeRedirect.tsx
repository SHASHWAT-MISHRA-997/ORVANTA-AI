'use client';

import { useRouter } from 'next/navigation';
import { useEffect } from 'react';

export default function HomeRedirect() {
  const router = useRouter();

  useEffect(() => {
    const token = localStorage.getItem('warops_token');
    router.replace(token ? '/dashboard' : '/login');
  }, [router]);

  return null;
}
