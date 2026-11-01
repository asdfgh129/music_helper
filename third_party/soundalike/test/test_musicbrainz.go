package main

import (
	"fmt"
	"log"
	"os"
	"testing"

	"musicbrainz.org/ws/2"
)

// TestMusicBrainzConnection 测试 MusicBrainz API 连接
func TestMusicBrainzConnection(t *testing.T) {
	log.Println("=" + "========================================")
	log.Println("开始测试 MusicBrainz 连接")
	log.Println("=" + "========================================")

	// 测试查询
	client := musicbrainz.NewClient("SoundAlike-Test/1.0")
	result, err := client.Query(musicbrainz.Query{
		Type:  "recording",
		Query: "recording:\"Love Story\" AND artist:\"Taylor Swift\"",
		Limit: 5,
	})

	if err != nil {
		t.Errorf("MusicBrainz 查询失败: %v", err)
		return
	}

	log.Printf("✓ MusicBrainz 查询成功! 找到 %d 条结果", len(result.Recordings))

	for i, rec := range result.Recordings {
		if i >= 3 {
			break
		}
		title := rec.Title
		artist := rec.ArtistCredits[0].Name
		log.Printf("  %d. %s - %s", i+1, title, artist)
	}

	log.Println("=" + "========================================")
	log.Println("✓ MusicBrainz 连接测试通过")
	log.Println("=" + "========================================")
}

// TestMusicBrainzDirect 直接测试 MusicBrainz Web API
func TestMusicBrainzDirect(t *testing.T) {
	log.Println("=" + "========================================")
	log.Println("测试 MusicBrainz 直接 API 连接")
	log.Println("=" + "========================================")

	// 直接使用 HTTP 客户端测试
	url := "https://musicbrainz.org/ws/2/recording?query=recording%3A%22Love+Story%22+AND+artist%3A%22Taylor+Swift%22&limit=5&fmt=json"

	resp, err := http.Get(url)
	if err != nil {
		t.Errorf("HTTP 请求失败: %v", err)
		return
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		t.Errorf("HTTP 状态码错误: %d", resp.StatusCode)
		return
	}

	log.Println("✓ MusicBrainz 直接 API 测试通过")
	log.Println("=" + "========================================")
}

func main() {
	// 运行测试
	tests := []testing.InternalTest{
		{"TestMusicBrainzConnection", TestMusicBrainzConnection},
	}

	os.Exit(testing.RunTests(tests, nil))
}
