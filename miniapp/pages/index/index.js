// pages/index/index.js — 首页
const app = getApp();

Page({
  data: {
    backendStatus: 'checking', // checking | online | offline
  },

  onShow() {
    this.checkBackend();
  },

  checkBackend() {
    const that = this;
    that.setData({ backendStatus: 'checking' });
    wx.request({
      url: `${app.globalData.baseUrl}/health`,
      method: 'GET',
      success(res) {
        if (res.statusCode === 200 && res.data.status === 'ok') {
          that.setData({ backendStatus: 'online' });
        } else {
          that.setData({ backendStatus: 'offline' });
        }
      },
      fail() {
        that.setData({ backendStatus: 'offline' });
      }
    });
  },

  goToUpload() {
    wx.navigateTo({ url: '/pages/upload/upload' });
  },
});
