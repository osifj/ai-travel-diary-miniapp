// ==========================================
// 统一 HTTP 请求工具
// ==========================================

const app = getApp();

/**
 * 基础请求封装
 * @param {string} url     - 接口路径 (如 /upload)
 * @param {string} method  - HTTP 方法
 * @param {object} data    - 请求体
 * @returns {Promise}
 */
function request(url, method = 'GET', data = {}) {
  const baseUrl = app ? app.globalData.baseUrl : 'http://127.0.0.1:8000';

  return new Promise((resolve, reject) => {
    wx.request({
      url: `${baseUrl}${url}`,
      method: method,
      data: data,
      header: {
        'Content-Type': 'application/json',
      },
      success(res) {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve(res.data);
        } else {
          reject({
            statusCode: res.statusCode,
            message: res.data.detail || '请求失败',
            data: res.data,
          });
        }
      },
      fail(err) {
        reject({
          statusCode: 0,
          message: err.errMsg || '网络请求失败',
          error: err,
        });
      },
    });
  });
}

/**
 * 上传文件
 * @param {string} filePath - 本地文件路径
 * @returns {Promise}
 */
function uploadFile(filePath) {
  const baseUrl = app ? app.globalData.baseUrl : 'http://127.0.0.1:8000';

  return new Promise((resolve, reject) => {
    wx.uploadFile({
      url: `${baseUrl}/upload`,
      filePath: filePath,
      name: 'file',
      success(res) {
        try {
          const data = JSON.parse(res.data);
          if (res.statusCode === 200 && data.success) {
            resolve(data);
          } else {
            reject({
              statusCode: res.statusCode,
              message: data.detail || '上传失败',
              data: data,
            });
          }
        } catch (e) {
          reject({
            statusCode: res.statusCode,
            message: '响应解析失败',
          });
        }
      },
      fail(err) {
        reject({
          statusCode: 0,
          message: err.errMsg || '上传失败',
          error: err,
        });
      },
    });
  });
}

module.exports = {
  request,
  uploadFile,
};
