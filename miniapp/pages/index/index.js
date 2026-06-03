// pages/index/index.js — 首页
const app = getApp();

Page({
  data: {
    backendStatus: 'checking', // checking | online | offline
    isBackendOnline: false,
    isBackendOffline: false,
    isBackendChecking: true,
  },

  onShow() {
    this.checkBackend();
  },

  checkBackend() {
    const that = this;
    that.setBackendStatus('checking');
    wx.request({
      url: `${app.globalData.baseUrl}/health`,
      method: 'GET',
      success(res) {
        if (res.statusCode === 200 && res.data.status === 'ok') {
          that.setBackendStatus('online');
        } else {
          that.setBackendStatus('offline');
        }
      },
      fail() {
        that.setBackendStatus('offline');
      }
    });
  },

  setBackendStatus(status) {
    this.setData({
      backendStatus: status,
      isBackendOnline: status === 'online',
      isBackendOffline: status === 'offline',
      isBackendChecking: status === 'checking',
    });
  },

  goToUpload() {
    wx.navigateTo({ url: '/pages/upload/upload' });
  },
});
