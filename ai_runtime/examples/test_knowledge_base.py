"""
知识库API测试示例脚本

演示如何使用知识库的各种功能
"""

import requests
import json
from pathlib import Path

# 配置
BASE_URL = "http://localhost:8000/api/v1/knowledge"


def print_response(title: str, response: requests.Response):
    """打印响应信息"""
    print(f"\n{'=' * 60}")
    print(f"📌 {title}")
    print(f"{'=' * 60}")
    print(f"状态码: {response.status_code}")
    if response.status_code < 400:
        print(f"响应:\n{json.dumps(response.json(), indent=2, ensure_ascii=False)}")
    else:
        print(f"错误: {response.text}")


def test_create_document():
    """测试创建文档"""
    response = requests.post(f"{BASE_URL}/documents", json={
        "title": "Python快速入门指南",
        "content": """
        Python是一种高级编程语言，具有简洁的语法和强大的功能。

        主要特点：
        1. 简单易学
        2. 功能强大
        3. 应用广泛

        快速开始：
        - 安装Python
        - 学习基础语法
        - 实践项目开发
        """,
        "source": "manual",
        "source_type": "manual",
        "access_level": "tenant",
        "auto_index": True,
        "metadata": {
            "category": "编程教程",
            "level": "入门",
            "language": "Python"
        }
    })
    print_response("创建文档", response)
    return response.json().get("id") if response.status_code == 201 else None


def test_upload_file(file_path: str):
    """测试文件上传"""
    if not Path(file_path).exists():
        print(f"\n⚠️  文件不存在: {file_path}")
        return None

    with open(file_path, "rb") as f:
        files = {"file": f}
        data = {
            "access_level": "tenant",
            "auto_index": "true"
        }
        response = requests.post(
            f"{BASE_URL}/documents/upload",
            files=files,
            data=data
        )
    print_response(f"上传文件: {file_path}", response)
    return response.json().get("id") if response.status_code == 201 else None


def test_create_from_url(url: str):
    """测试从URL创建"""
    response = requests.post(
        f"{BASE_URL}/documents/from-url",
        data={
            "url": url,
            "access_level": "tenant",
            "auto_index": "true"
        }
    )
    print_response(f"从URL创建: {url}", response)
    return response.json().get("id") if response.status_code == 201 else None


def test_list_documents():
    """测试列出文档"""
    response = requests.get(
        f"{BASE_URL}/documents",
        params={
            "page": 1,
            "page_size": 10
        }
    )
    print_response("列出文档", response)


def test_search_documents(query: str):
    """测试搜索文档"""
    response = requests.post(
        f"{BASE_URL}/documents/search",
        json={
            "query": query,
            "top_k": 5
        }
    )
    print_response(f"搜索: {query}", response)

    if response.status_code == 200:
        results = response.json()
        print("\n🔍 搜索结果详情:")
        for i, result in enumerate(results["results"], 1):
            doc = result["document"]
            score = result["score"]
            print(f"\n{i}. {doc['title']}")
            print(f"   相似度: {score:.3f}")
            print(f"   来源: {doc['source_type']}")
            print(f"   摘要: {doc['content'][:100]}...")


def test_get_document(doc_id: str):
    """测试获取文档"""
    response = requests.get(f"{BASE_URL}/documents/{doc_id}")
    print_response(f"获取文档: {doc_id}", response)


def test_update_document(doc_id: str):
    """测试更新文档"""
    response = requests.put(
        f"{BASE_URL}/documents/{doc_id}",
        json={
            "title": "Python快速入门指南 v2.0",
            "content": "更新后的内容...",
            "re_index": True
        }
    )
    print_response(f"更新文档: {doc_id}", response)


def test_batch_create():
    """测试批量创建"""
    documents = [
        {
            "title": f"测试文档 {i}",
            "content": f"这是第 {i} 个测试文档的内容",
            "access_level": "tenant",
            "auto_index": True
        }
        for i in range(1, 6)
    ]

    response = requests.post(
        f"{BASE_URL}/documents/batch",
        json={"documents": documents}
    )
    print_response("批量创建 5个文档", response)


def test_get_stats():
    """测试获取统计信息"""
    response = requests.get(f"{BASE_URL}/stats")
    print_response("知识库统计", response)


def test_delete_document(doc_id: str):
    """测试删除文档"""
    response = requests.delete(f"{BASE_URL}/documents/{doc_id}")
    print_response(f"删除文档: {doc_id}", response)


def main():
    """主函数：运行所有测试"""
    print("🚀 开始测试知识库API")
    print("=" * 60)

    # 1. 创建文档
    doc_id = test_create_document()

    # 2. 批量创建
    test_batch_create()

    # 3. 列出所有文档
    test_list_documents()

    # 4. 搜索文档
    test_search_documents("Python 编程")
    test_search_documents("如何快速开始学习")

    # 5. 获取统计信息
    test_get_stats()

    # 6. 获取单个文档
    if doc_id:
        test_get_document(doc_id)

        # 7. 更新文档
        test_update_document(doc_id)

        # 8. 再次获取查看更新结果
        test_get_document(doc_id)

        # 9. 删除文档（可选）
        # test_delete_document(doc_id)

    # 10. 文件上传示例（需要实际文件）
    # test_upload_file("example.pdf")

    # 11. URL抓取示例
    # test_create_from_url("https://example.com/docs")

    print("\n" + "=" * 60)
    print("✅ 测试完成！")
    print("=" * 60)
    print("\n💡 提示:")
    print("1. 访问 http://localhost:8000/docs 查看完整API文档")
    print("2. 使用 test_upload_file() 测试文件上传功能")
    print("3. 使用 test_create_from_url() 测试URL抓取功能")


if __name__ == "__main__":
    try:
        main()
    except requests.exceptions.ConnectionError:
        print("\n❌ 错误: 无法连接到服务器")
        print("请确保服务已启动: python ai_runtime/main.py")
    except Exception as e:
        print(f"\n❌ 发生错误: {e}")
        import traceback
        traceback.print_exc()
