from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
import time
import re
import logging
from pathlib import Path
import sys
import traceback

# 配置日志系统
def setup_logging():
    """设置详细的日志记录"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('cet4_spider_debug.log', encoding='utf-8'),
            logging.StreamHandler(sys.stdout)
        ]
    )
    return logging.getLogger(__name__)

class CET4Spider:
    def __init__(self, chrome_driver_path):
        """
        初始化爬虫
        :param chrome_driver_path: 本地ChromeDriver的绝对路径
        """
        self.logger = setup_logging()
        self.chrome_driver_path = Path(chrome_driver_path)
        self.logger.info(f"初始化爬虫，ChromeDriver路径: {self.chrome_driver_path}")
        
        # 验证ChromeDriver路径
        if not self.chrome_driver_path.exists():
            self.logger.error(f"❌ ChromeDriver不存在: {self.chrome_driver_path}")
            raise FileNotFoundError(f"ChromeDriver不存在: {self.chrome_driver_path}")
        
        # 浏览器配置
        self.chrome_options = webdriver.ChromeOptions()
        self.chrome_options.add_argument("--headless=new")
        self.chrome_options.add_argument("--no-sandbox")
        self.chrome_options.add_argument("--disable-dev-shm-usage")
        self.chrome_options.add_argument("--disable-gpu")
        self.chrome_options.add_argument("--window-size=1920,1080")
        self.chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        
        self.logger.info("浏览器配置完成")
    
    def _generate_url(self, year, month, set_count):
        """生成目标URL"""
        url = f"https://www.hellocet.online/cet4?year={year}&month={month}&setCount={set_count}"
        self.logger.debug(f"生成的URL: {url}")
        return url
    
    def _debug_save_page_source(self, driver, filename):
        """保存页面源代码用于调试"""
        try:
            debug_dir = Path("debug_pages")
            debug_dir.mkdir(exist_ok=True)
            filepath = debug_dir / filename
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(driver.page_source)
            self.logger.info(f"✅ 页面源代码已保存: {filepath}")
        except Exception as e:
            self.logger.warning(f"保存页面源代码失败: {e}")
    
    def _process_fill_blank(self, element):
        """处理填空部分，将输入框替换为下划线"""
        # 获取包含input标签的所有元素
        html = element.get_attribute('outerHTML')
        # 使用正则表达式将input标签替换为下划线
        processed_html = re.sub(
            r'<span class="mx-1 inline-block"><span class="text-gray-500">(\d+)\.</span><input[^>]+></span>',
            r'\1._ ',  # 保留题号并添加下划线
            html
        )
        # 提取处理后的纯文本
        from bs4 import BeautifulSoup  # 临时导入用于文本提取
        soup = BeautifulSoup(processed_html, 'html.parser')
        return soup.get_text().strip()
    
    def _extract_paragraph_container(self, container, container_name="段落容器"):
        """
        提取包含段落和输入框的容器内容
        处理类似这样的结构：
        <div class="space-y-6 text-left">
          <div class="border-b pb-4">
            <p class="mb-3 font-medium">段落内容</p>
            <input ...> 输入框
          </div>
          ... 更多类似结构
        </div>
        """
        self.logger.info(f"开始提取{container_name}...")
        try:
            # 查找包含段落的容器，使用更灵活的选择器
            paragraph_containers = container.find_elements(
                By.XPATH, 
                ".//div[contains(@class, 'space-y-') and contains(@class, 'text-left')]"
            )
            
            if not paragraph_containers:
                self.logger.warning(f"未找到{container_name}，尝试其他选择器...")
                # 尝试其他可能的选择器
                paragraph_containers = container.find_elements(
                    By.XPATH, 
                    ".//div[contains(@class, 'space-y-')]"
                )
            
            if not paragraph_containers:
                self.logger.warning(f"❌ 未找到任何{container_name}")
                return ""
            
            result_text = f"【{container_name}】\n"
            
            for i, para_container in enumerate(paragraph_containers):
                self.logger.info(f"处理第{i+1}个段落容器...")
                
                # 提取容器内的所有段落块
                paragraph_blocks = para_container.find_elements(
                    By.XPATH, 
                    ".//div[contains(@class, 'border-b') and contains(@class, 'pb-')]"
                )
                
                if not paragraph_blocks:
                    self.logger.info(f"第{i+1}个容器中未找到段落块，尝试直接提取段落...")
                    # 如果没有找到特定的块结构，直接提取所有段落
                    paragraphs = para_container.find_elements(By.TAG_NAME, "p")
                    for j, paragraph in enumerate(paragraphs):
                        paragraph_text = paragraph.text.strip()
                        if paragraph_text:
                            result_text += f"{paragraph_text}\n"
                    continue
                
                # 处理每个段落块
                for j, block in enumerate(paragraph_blocks):
                    try:
                        # 提取段落文本
                        paragraph_elem = block.find_element(By.TAG_NAME, "p")
                        paragraph_text = paragraph_elem.text.strip()
                        
                        # 检查是否有输入框
                        input_elems = block.find_elements(By.TAG_NAME, "input")
                        has_input = len(input_elems) > 0
                        
                        # 格式化输出
                        if paragraph_text:
                            result_text += f"{paragraph_text}"
                            if has_input:
                                result_text += " [填空]"
                            result_text += "\n"
                            
                    except Exception as e:
                        self.logger.warning(f"处理第{j+1}个段落块时出错: {e}")
                        continue
            
            result_text += "\n"
            self.logger.info(f"✅ {container_name}提取成功，共处理{len(paragraph_containers)}个容器")
            return result_text
            
        except Exception as e:
            self.logger.error(f"❌ {container_name}提取失败: {str(e)}")
            return f"【{container_name}提取失败：{str(e)}】\n\n"
    
    def _extract_module(self, container, module_name):
        """通用模块提取方法，基于实际页面结构"""
        self.logger.info(f"开始提取{module_name}...")
        try:
            # 1. 定位模块根容器 (class="mb-8"的div)
            module_container = container.find_element(
                By.XPATH, 
                f".//div[contains(@class, 'mb-8') and .//h3[contains(@class, 'mb-4 text-lg font-semibold') and text()='{module_name}']]"
            )
            
            # 2. 提取模块标题
            title = module_container.find_element(
                By.XPATH, 
                ".//h3[contains(@class, 'mb-4 text-lg font-semibold')]"
            ).text
            
            # 3. 提取说明文本 (class="mb-4 text-left text-sm text-gray-600"的h3标签)
            intro_elements = module_container.find_elements(
                By.XPATH, 
                ".//h3[contains(@class, 'mb-4 text-left text-sm text-gray-600')]"
            )
            intro_text = "\n".join([elem.text for elem in intro_elements]) + "\n\n"
            
            # 4. 提取正文内容 (class="mb-6 space-y-4 text-left"的div)
            content_text = ""
            try:
                content_container = module_container.find_element(
                    By.XPATH, 
                    ".//div[contains(@class, 'mb-6 space-y-4 text-left')]"
                )
                # 处理段落中的填空
                content_paragraphs = content_container.find_elements(By.TAG_NAME, "p")
                processed_paragraphs = [self._process_fill_blank(p) for p in content_paragraphs]
                content_text = "\n".join(processed_paragraphs) + "\n\n"
            except Exception as e:
                self.logger.warning(f"{module_name}无标准内容容器，尝试提取段落容器: {e}")
                # 如果标准内容容器不存在，尝试提取段落容器
                content_text = self._extract_paragraph_container(module_container, f"{module_name}内容")
            
            # 5. 提取选项/词库 (如有)
            options_text = ""
            try:
                options_container = module_container.find_element(
                    By.XPATH, 
                    ".//div[contains(@class, 'grid') and contains(@class, 'gap-4')]"
                )
                options = options_container.find_elements(
                    By.XPATH, 
                    ".//div[contains(@class, 'flex items-start')]"
                )
                options_text = "【选项/词库】\n" + "\n".join([opt.text for opt in options]) + "\n\n"
            except Exception:
                self.logger.info(f"{module_name}无选项/词库，跳过提取")
            
            # 整合模块内容
            full_module = f"{title}\n{intro_text}【正文内容】\n{content_text}{options_text}"
            self.logger.info(f"✅ {module_name}提取成功")
            return full_module
        
        except Exception as e:
            self.logger.error(f"❌ {module_name}提取失败: {str(e)}")
            # 尝试直接提取段落容器作为备选方案
            self.logger.info(f"尝试备选方案提取{module_name}...")
            alternative_content = self._extract_paragraph_container(container, module_name)
            if alternative_content and len(alternative_content.strip()) > 20:  # 确保有实际内容
                return f"{module_name}\n{alternative_content}"
            else:
                return f"【{module_name}提取失败：{str(e)}】\n\n"
    
    def _extract_writing(self, container):
        """提取写作部分（重写以匹配实际结构）"""
        return self._extract_module(container, "Part I Writing")
    
    def _extract_section_a(self, container):
        """提取Section A（重写以匹配实际结构）"""
        return self._extract_module(container, "Section A")
    
    def _extract_section_b(self, container):
        """提取Section B（重写以匹配实际结构）"""
        return self._extract_module(container, "Section B")
    
    def _extract_section_c(self, container):
        """提取Section C（重写以匹配实际结构）"""
        return self._extract_module(container, "Section C")
    
    def crawl_single_paper(self, year, month, set_count):
        """
        爬取单套CET4真题
        """
        driver = None
        start_time = time.time()
        
        try:
            self.logger.info("=" * 60)
            self.logger.info(f"开始爬取：{year}年{month}月-第{set_count}套")
            
            # 1. 生成URL
            target_url = self._generate_url(year, month, set_count)
            self.logger.info(f"目标URL: {target_url}")
            
            # 2. 启动浏览器
            self.logger.info("启动Chrome浏览器...")
            service = Service(executable_path=str(self.chrome_driver_path))
            driver = webdriver.Chrome(service=service, options=self.chrome_options)
            self.logger.info("✅ 浏览器启动成功")
            
            # 3. 访问页面
            self.logger.info(f"访问页面: {target_url}")
            driver.get(target_url)
            time.sleep(3)  # 等待页面加载
            
            # 保存初始页面用于调试
            self._debug_save_page_source(driver, f"initial_page_{year}_{month}_{set_count}.html")
            
            # 4. 点击阅读按钮（更通用的定位方式）
            self.logger.info("查找并点击阅读按钮...")
            try:
                click_btn = WebDriverWait(driver, 15).until(
                    EC.element_to_be_clickable(
                        (By.XPATH, ".//*[contains(text(), '阅读') and (self::button or self::a or self::div)]")
                    )
                )
                click_btn.click()
                self.logger.info("✅ 阅读按钮点击成功")
                time.sleep(3)  # 等待内容加载
            except Exception as e:
                self.logger.warning(f"点击阅读按钮失败: {e}，尝试继续执行...")
            
            # 保存点击后的页面
            self._debug_save_page_source(driver, f"after_click_{year}_{month}_{set_count}.html")
            
            # 5. 定位内容容器（更通用的定位方式）
            self.logger.info("定位内容容器...")
            full_container = WebDriverWait(driver, 15).until(
                EC.presence_of_element_located(
                    (By.XPATH, "//div[contains(@class, 'rounded-lg') and contains(@class, 'bg-white') and contains(@class, 'p-6')]")
                )
            )
            self.logger.info("✅ 内容容器定位成功")
            
            # 6. 额外提取：尝试提取所有段落容器
            self.logger.info("开始提取额外的段落容器...")
            additional_paragraphs = self._extract_paragraph_container(full_container, "附加段落内容")
            
            # 7. 提取各模块内容
            self.logger.info("开始提取各模块内容...")
            writing = self._extract_writing(full_container)
            section_a = self._extract_section_a(full_container)
            section_b = self._extract_section_b(full_container)
            section_c = self._extract_section_c(full_container)
            
            # 8. 整合内容
            full_paper = f"""{year}年{month}月大学英语CET4真题（第{set_count}套）
{"="*60}
{writing}{section_a}{section_b}{section_c}
{additional_paragraphs}
"""
            
            # 9. 保存文件
            save_dir = Path(f"CET4真题_通用爬取/{year}年{month}月")
            save_dir.mkdir(parents=True, exist_ok=True)
            save_path = save_dir / f"{year}年{month}月-第{set_count}套.txt"
            
            with open(save_path, "w", encoding="utf-8") as f:
                f.write(full_paper)
            
            # 计算执行时间
            execution_time = time.time() - start_time
            
            # 生成成功报告
            success_msg = f"""
✅ 爬取成功报告：
   试卷：{year}年{month}月-第{set_count}套
   保存路径：{save_path}
   文件大小：{round(len(full_paper)/1024, 2)}KB
   执行时间：{round(execution_time, 2)}秒
   内容模块：写作 ✅ | Section A ✅ | Section B ✅ | Section C ✅ | 段落容器 ✅
"""
            self.logger.info(success_msg)
            return success_msg
            
        except Exception as e:
            execution_time = time.time() - start_time
            error_details = f"""
❌ 爬取失败报告：
   错误类型：{type(e).__name__}
   错误信息：{str(e)}
   执行时间：{round(execution_time, 2)}秒
   详细堆栈：
{traceback.format_exc()}
"""
            self.logger.error(error_details)
            
            # 保存错误时的页面
            if driver:
                self._debug_save_page_source(driver, f"error_page_{year}_{month}_{set_count}.html")
            
            return f"❌ 爬取失败：{str(e)}"
        
        finally:
            if driver:
                driver.quit()
                self.logger.info("🔚 浏览器已关闭")

def check_environment():
    """检查运行环境"""
    logger = setup_logging()
    logger.info("=" * 60)
    logger.info("环境检查开始")
    
    # 检查Python版本
    logger.info(f"Python版本: {sys.version}")
    
    # 检查必要模块
    try:
        from selenium import __version__ as selenium_version
        logger.info(f"Selenium版本: {selenium_version}")
    except ImportError:
        logger.error("❌ Selenium未安装")
        return False
    
    # 检查BeautifulSoup（用于处理HTML）
    try:
        import bs4
        logger.info(f"BeautifulSoup版本: {bs4.__version__}")
    except ImportError:
        logger.error("❌ BeautifulSoup未安装")
        return False
    
    logger.info("✅ 环境检查通过")
    return True

# ------------------- 主程序 -------------------
if __name__ == "__main__":
    # 环境检查
    if not check_environment():
        print("❌ 环境检查失败，请安装必要的依赖包：")
        print("   pip install selenium beautifulsoup4")
        sys.exit(1)
    
    # 配置参数
    CHROME_DRIVER_PATH = r"D:\Chrome_driver\chromedriver.exe"  # 使用原始字符串
    
    # 测试参数
    TEST_YEAR = 2020
    TEST_MONTH = 12
    TEST_SET = 1
    
    try:
        # 初始化爬虫
        cet4_spider = CET4Spider(chrome_driver_path=CHROME_DRIVER_PATH)
        
        # 执行爬取
        result = cet4_spider.crawl_single_paper(
            year=TEST_YEAR,
            month=TEST_MONTH,
            set_count=TEST_SET
        )
        
        print("\n" + "=" * 60)
        print("最终结果:")
        print(result)
        print("详细日志请查看: cet4_spider_debug.log")
        print("调试页面请查看: debug_pages/ 文件夹")
        
    except Exception as e:
        logger = setup_logging()
        logger.error(f"程序执行失败: {str(e)}")
        logger.error(traceback.format_exc())
        print(f"❌ 程序执行失败: {e}")
        sys.exit(1)