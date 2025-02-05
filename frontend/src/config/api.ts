// 这行代码定义了一个API基础URL常量
// 它首先尝试使用环境变量NEXT_PUBLIC_API_BASE_URL作为API地址
// 如果环境变量不存在,则使用默认值'http://localhost:8000'
// 这样可以在开发环境和生产环境使用不同的API地址
export const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000';