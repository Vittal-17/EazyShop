// src/context/AuthContext.js
import { createContext, useEffect, useState, useMemo } from 'react';
import axios from 'axios';
import toast from 'react-hot-toast';
import { useNavigate } from 'react-router-dom';

const API_URL = process.env.REACT_APP_API_URL || 'http://127.0.0.1:8000';
export const AuthContext = createContext();

// ==========================================
// 🚀 AXIOS REFRESH QUEUE STATE
// ==========================================
let isRefreshing = false;
let failedQueue = [];

const processQueue = (error, token = null) => {
  failedQueue.forEach(prom => {
    if (error) {
      prom.reject(error);
    } else {
      prom.resolve(token);
    }
  });
  failedQueue = [];
};

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  const navigate = useNavigate();

  // 1. CREATE AXIOS INSTANCE WITH COOKIE CREDENTIALS
  const axiosInstance = useMemo(() => {
    const instance = axios.create({
      baseURL: API_URL,
      withCredentials: true, // 🚀 Automatically attaches HTTP-Only cookies
    });

    // Response Interceptor for 401 Silent Refresh & Session Expiration
    instance.interceptors.response.use(
      (response) => response,
      async (error) => {
        const originalRequest = error.config;

        if (error.response?.status === 401 && !originalRequest._retry) {
          if (isRefreshing) {
            return new Promise(function(resolve, reject) {
              failedQueue.push({ resolve, reject });
            }).then(() => {
              return instance(originalRequest);
            }).catch(err => {
              return Promise.reject(err);
            });
          }

          originalRequest._retry = true;
          isRefreshing = true;

          try {
            await instance.post('/api/token/refresh/');
            processQueue(null);
            return instance(originalRequest);
          } catch (refreshErr) {
            processQueue(refreshErr, null);
            localStorage.removeItem('user');
            setUser(null);

            toast.error('⏳ Session Expired, Please Log in Again', {
              duration: 4000,
            });

            navigate('/login');
            return Promise.reject(refreshErr);
          } finally {
            isRefreshing = false;
          }
        }
        return Promise.reject(error);
      }
    );

    return instance;
  }, [navigate]);

  // 🚀 HELPER: Fetch absolute latest user profile from backend database
  const refreshUser = async () => {
    try {
      const storedUser = localStorage.getItem('user');
      if (storedUser) {
        const parsedUser = JSON.parse(storedUser);
        if (parsedUser && parsedUser.id) {
          const response = await axiosInstance.get(`/api/users/${parsedUser.id}/`);
          setUser(response.data);
          localStorage.setItem('user', JSON.stringify(response.data));
          return response.data;
        }
      }
    } catch (err) {
      console.error('Failed to refresh user profile:', err);
    }
    return null;
  };

  // 2. HYDRATION & PRODUCTION FRESHNESS CHECK ON MOUNT
  useEffect(() => {
    const initializeAuth = async () => {
      const storedUser = localStorage.getItem('user');

      if (storedUser) {
        try {
          const parsedUser = JSON.parse(storedUser);
          setUser(parsedUser);

          // Always fetch fresh data on mount to prevent production caching desync
          if (parsedUser && parsedUser.id) {
            const response = await axiosInstance.get(`/api/users/${parsedUser.id}/`);
            setUser(response.data);
            localStorage.setItem('user', JSON.stringify(response.data));
          }
        } catch (error) {
          console.error('Session initialization error:', error);
          localStorage.removeItem('user');
          setUser(null);
        }
      }
      setLoading(false);
    };

    initializeAuth();
  }, [axiosInstance]);

  // 3. LOGIN USER METHOD
  const loginUser = async (email, password) => {
    try {
      const res = await axios.post(
        `${API_URL}/api/token/`,
        { email, password },
        { withCredentials: true }
      );

      if (res.status === 200) {
        const { user: userData } = res.data;

        localStorage.setItem('user', JSON.stringify(userData));
        setUser(userData);

        // Guest cart sync algorithm
        const tempCart = JSON.parse(localStorage.getItem('tempCart')) || [];

        if (tempCart.length > 0) {
          toast('Syncing your guest cart...', { icon: '🔄' });

          for (const item of tempCart) {
            try {
              await axiosInstance.post('/api/cart-items/', {
                product: item.product,
                quantity: item.quantity,
              });
            } catch (err) {
              console.error(`Failed to sync product ${item.product}`, err);
            }
          }

          localStorage.removeItem('tempCart');
          toast.success('✨ Cart synced successfully!');
        }

        return true;
      }
    } catch (err) {
      console.error('Login failed:', err.response?.data || err.message);
    }
    return false;
  };

  // 4. CROSS-TAB WALLET SYNC (BroadcastChannel)
  useEffect(() => {
    const channel = new BroadcastChannel('eazyshop_wallet_sync');
    channel.onmessage = (event) => {
      if (event.data?.type === 'SYNC_WALLET') {
        setUser((prevUser) => {
          if (prevUser && prevUser.id === event.data.userId) {
            const updatedUser = { ...prevUser, wallet_balance: event.data.newBalance };
            localStorage.setItem('user', JSON.stringify(updatedUser));
            return updatedUser;
          }
          return prevUser;
        });
      }
    };
    return () => channel.close();
  }, []);

  const syncWalletBalance = (userId, newBalance) => {
    setUser((prev) => {
      const updatedUser = prev ? { ...prev, wallet_balance: newBalance } : prev;
      if (updatedUser) localStorage.setItem('user', JSON.stringify(updatedUser));
      return updatedUser;
    });
    const channel = new BroadcastChannel('eazyshop_wallet_sync');
    channel.postMessage({ type: 'SYNC_WALLET', userId, newBalance });
    channel.close();
  };

  // 5. LOGOUT USER METHOD
  const logoutUser = async () => {
    try {
      await axiosInstance.post('/api/logout/');
    } catch (err) {
      console.error('Logout error:', err);
    } finally {
      setUser(null);
      localStorage.removeItem('user');
      navigate('/login');
    }
  };

  return (
    <AuthContext.Provider value={{ user, setUser, loginUser, logoutUser, axiosInstance, syncWalletBalance, refreshUser }}>
      {!loading && children}
    </AuthContext.Provider>
  );
};

export default AuthContext;